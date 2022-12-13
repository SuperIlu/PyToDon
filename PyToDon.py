import sys
import time
import re
import datetime

from mastodon import Mastodon
from escpos.printer import Usb
import urllib.request
from PIL import Image
from io import StringIO
from html.parser import HTMLParser
import pygame

MASTODON_SERVER = "https://mastodon.social"

CHECK_DELAY = 10
X_START = 60
Y_START = 40

WIDTH = 640 - 20
HEIGHT = 480 - 20
LIMAGE_SIZE = 240
SIMAGE_SIZE = 60

LFONT = 32
SFONT = 24

FG = pygame.Color(255, 255, 255)
BG = pygame.Color(32, 32, 32)


last_not_id = None
last_not_check = None
last_toot_id = None
last_toot_check = None


class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.reset()
        self.strict = False
        self.convert_charrefs = True
        self.text = StringIO()

    def handle_data(self, d):
        self.text.write(d)

    def get_data(self):
        return self.text.getvalue()


def strip_tags(html):
    s = MLStripper()
    s.feed(html.replace("</p>", "</p> "))
    string_unicode = s.get_data()
    text = filter_unicode(string_unicode)
    return re.sub(r"http\S+", "", text)


def filter_unicode(txt):
    return "".join(filter(lambda x: ord(x) < 0xFFFF, txt))


def register_app():
    Mastodon.create_app("pytooterapp", api_base_url=MASTODON_SERVER, to_file="pytooter_clientcred.secret")
    print("App registered")


def login_app(user, pw):
    mastodon = Mastodon(client_id="pytooter_clientcred.secret", api_base_url=MASTODON_SERVER)
    mastodon.log_in(user, pw, to_file="pytooter_usercred.secret")
    print("Login for '{}' succesfull".format(user))


def main_app():
    global last_not_check, last_toot_check

    printer = Usb(0x0416, 0x5011, profile="POS-5890")
    mastodon = Mastodon(access_token="pytooter_usercred.secret", api_base_url=MASTODON_SERVER)

    screen = pygame.display.set_mode((0, 0), flags=pygame.FULLSCREEN)
    pygame.init()
    pygame.display.set_caption("PyToDon")
    pygame.mouse.set_visible(False)

    last_not_check = datetime.datetime.now()
    last_toot_check = datetime.datetime.now()

    keep_running = True
    input_mode = False
    toot_txt = ""
    myfont_small = pygame.font.SysFont(pygame.font.get_default_font(), SFONT)
    myfont_large = pygame.font.SysFont(pygame.font.get_default_font(), LFONT)
    while keep_running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                keep_running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    keep_running = False
                elif event.key == pygame.K_BACKSPACE:
                    toot_txt = toot_txt[:-1]
                elif event.key == pygame.K_RETURN:
                    if input_mode:
                        input_mode = False
                        if len(toot_txt) > 0:
                            mastodon.toot(toot_txt)
                        toot_txt = ""
                    else:
                        input_mode = True
                else:
                    toot_txt += event.unicode

        # display either latest toot or current text
        if not input_mode:
            check_timeline(mastodon, screen)
        else:
            screen.fill(BG)
            wrapped = wrap_text("ENTER TOOT:", myfont_large, WIDTH)
            cont = render_text_list(wrapped, myfont_large)
            screen.blit(cont, (X_START, Y_START))

            wrapped = wrap_text(toot_txt, myfont_small, WIDTH)
            cont = render_text_list(wrapped, myfont_small)
            screen.blit(cont, (X_START, Y_START + LFONT + SFONT))
            pygame.display.flip()

        check_notifications(mastodon, printer)

    pygame.quit()
    quit()


def check_timeline(mastodon, screen):
    global last_toot_id, last_toot_check

    elapsed = datetime.datetime.now() - last_toot_check
    if elapsed > datetime.timedelta(seconds=CHECK_DELAY):
        last_toot_check = datetime.datetime.now()
        my_tl = mastodon.timeline()
        if len(my_tl) > 0:
            # print("{}".format(my_tl))
            t = my_tl[0]  # get most recent toot
            if last_toot_id != t["id"]:
                last_toot_id = t["id"]
                show_toot(screen, t)
            else:
                print("No new toots")


def check_notifications(mastodon, printer):
    global last_not_id, last_not_check

    elapsed = datetime.datetime.now() - last_not_check
    if elapsed > datetime.timedelta(seconds=CHECK_DELAY):
        last_not_check = datetime.datetime.now()
        my_nots = mastodon.notifications()
        if len(my_nots) > 0:
            # print("{}".format(my_nots))
            n = my_nots[0]  # get most recent notification
            if last_not_id != n["id"]:
                last_not_id = n["id"]
                print_notification(printer, n)
            else:
                print("No new notification")


def show_toot(s, t):
    print("Showing toot from {} at {}: {}".format(t["account"]["acct"], t["created_at"], t["id"]))
    print(t)

    s.fill(BG)

    if t["reblog"]:
        large_image = t["reblog"]["account"]["avatar_static"]
        small_image = t["account"]["avatar_static"]
        header = filter_unicode("{} boosted".format(t["account"]["acct"]))
        toot_text = strip_tags(t["reblog"]["content"])
    else:
        large_image = t["account"]["avatar_static"]
        small_image = None
        header = filter_unicode(t["account"]["acct"])
        toot_text = strip_tags(t["content"])

    size = LIMAGE_SIZE, LIMAGE_SIZE
    urllib.request.urlretrieve(large_image, "temp.image")
    img = Image.open("temp.image")
    img.thumbnail(size)
    img.save("temp.png", "PNG")
    image = pygame.image.load("temp.png")
    s.blit(image, (X_START, Y_START))
    print("large image drawn")

    if small_image:
        size = SIMAGE_SIZE, SIMAGE_SIZE
        urllib.request.urlretrieve(small_image, "temps.image")
        img = Image.open("temps.image")
        img.thumbnail(size)
        img.save("temps.png", "PNG")
        image = pygame.image.load("temps.png")
        s.blit(image, (X_START + LIMAGE_SIZE + (WIDTH - LIMAGE_SIZE) / 2, Y_START * 2))
        print("small image drawn")

    # print("\n\nTOOT is\n {}".format(toot_text))
    # print("HEADER is\n {}".format(header))

    myfont_large = pygame.font.SysFont(pygame.font.get_default_font(), LFONT)
    myfont_small = pygame.font.SysFont(pygame.font.get_default_font(), SFONT)

    if header:
        wrapped = wrap_text(header, myfont_large, WIDTH - LIMAGE_SIZE)
        cont = render_text_list(wrapped, myfont_large)
        s.blit(cont, (X_START + LIMAGE_SIZE, 200))

    wrapped = wrap_text(toot_text, myfont_small, WIDTH)
    cont = render_text_list(wrapped, myfont_small)
    s.blit(cont, (X_START, Y_START + LIMAGE_SIZE))
    pygame.display.flip()


# from https://github.com/ColdrickSotK/yamlui/blob/master/yamlui/util.py#L82-L143
#  GPL-2.0 license
def wrap_text(text, font, width):
    """Wrap text to fit inside a given width when rendered.
    :param text: The text to be wrapped.
    :param font: The font the text will be rendered in.
    :param width: The width to wrap to.
    """
    text_lines = text.replace("\t", "    ").split("\n")
    if width is None or width == 0:
        return text_lines

    wrapped_lines = []
    for line in text_lines:
        line = line.rstrip() + " "
        if line == " ":
            wrapped_lines.append(line)
            continue

        # Get the leftmost space ignoring leading whitespace
        start = len(line) - len(line.lstrip())
        start = line.index(" ", start)
        while start + 1 < len(line):
            # Get the next potential splitting point
            next = line.index(" ", start + 1)
            if font.size(line[:next])[0] <= width:
                start = next
            else:
                wrapped_lines.append(line[:start])
                line = line[start + 1 :]
                start = line.index(" ")
        line = line[:-1]
        if line:
            wrapped_lines.append(line)
    return wrapped_lines


# from https://github.com/ColdrickSotK/yamlui/blob/master/yamlui/util.py#L82-L143
#  GPL-2.0 license
def render_text_list(lines, font, fg=(255, 255, 255)):
    """Draw multiline text to a single surface with a transparent background.
    Draw multiple lines of text in the given font onto a single surface
    with no background colour, and return the result.
    :param lines: The lines of text to render.
    :param font: The font to render in.
    :param colour: The colour to render the font in, default is white.
    """
    rendered = [font.render(line, True, fg).convert_alpha() for line in lines]

    line_height = font.get_linesize()
    width = max(line.get_width() for line in rendered)
    tops = [int(round(i * line_height)) for i in range(len(rendered))]
    height = tops[-1] + font.get_height()

    surface = pygame.Surface((width, height)).convert_alpha()
    surface.fill((0, 0, 0, 0))
    for y, line in zip(tops, rendered):
        surface.blit(line, (0, y))

    return surface


def print_post(printer, n, txt):
    printer.set(font="a", align="center", bold=False, double_height=False)
    printer.text(n["account"]["display_name"] + "\n")
    printer.text(n["account"]["acct"] + "\n")
    printer.set(font="a", align="center", bold=True, double_height=False)
    printer.text("{}\n".format(txt))
    printer.set(font="b", align="left", bold=True, double_height=False)
    printer.text(strip_tags(n["status"]["content"]))


def print_notification(printer, n):
    print("Got {} from {} at {}: {}".format(n["type"], n["account"]["acct"], n["created_at"], n["id"]))

    # print avatar
    size = 128, 128
    urllib.request.urlretrieve(n["account"]["avatar_static"], "temp.image")
    img = Image.open("temp.image")
    img.thumbnail(size)
    printer.image(img)

    if n["type"] == "follow":
        printer.set(font="a", align="center", bold=False, double_height=False)
        printer.text(n["account"]["display_name"] + "\n")
        printer.text(n["account"]["acct"] + "\n")
        printer.set(font="a", align="center", bold=True, double_height=False)
        printer.text("Followed you\n")
    elif n["type"] == "favourite":
        print_post(printer, n, "favourited")
    elif n["type"] == "reblog":
        print_post(printer, n, "boosted")
    elif n["type"] == "mention":
        print_post(printer, n, "mentioned you")
    else:
        printer.set(font="a", align="center", bold=False, double_height=False)
        printer.text(n["account"]["display_name"] + "\n")
        printer.text(n["account"]["acct"] + "\n")
        printer.set(font="a", align="center", bold=True, double_height=False)
        printer.text(n["type"])

    # print line
    printer.ln()
    printer.set(font="b", align="right", bold=True, double_height=False)
    printer.text("========================================\n")
    printer.ln()


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "register":
        register_app
    elif len(sys.argv) == 4 and sys.argv[1] == "login":
        login_app(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 2 and sys.argv[1] == "run":
        main_app()
    else:
        print("Usage:")
