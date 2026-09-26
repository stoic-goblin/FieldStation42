import sys
from pathlib import Path
import glfw

from render import Text, create_window, clear_screen
from logo_display import LogoDisplay, LogoDisplayConfig
from OpenGL.GL import *

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from fs42.station_manager import StationManager
from fs42.osd.content_classifier import (
    ContentClassifier,
    ContentType,
    classify_current_content,
)

from fs42.osd.status_display import (
    CONFIG_FILE_PATH,
    SOCKET_FILE,
    ChannelStatusTracker,
    HAlignment,
    StatusDisplayConfig,
    VAlignment,
    read_status,
)

class StatusDisplay(object):
    def __init__(self, window, config: StatusDisplayConfig):
        self.config = config
        self.window = window

        self._text = Text(
            window,
            "",
            font_size=self.config.font_size,
            color=self.config.text_color,
            expansion_factor=self.config.expansion_factor,
            font=self.config.font,
        )

        self.time_since_change = 0
        self._tracker = ChannelStatusTracker()

        self.check_status()

    def check_status(self, socket_file=SOCKET_FILE):
        status = read_status(socket_file)
        if status is None:
            return
        new_string = self._tracker.changed_text(self.config, status)
        if new_string:
            self.time_since_change = -self.config.delay
            self._text.string = new_string

    def update(self, dt):
        self.time_since_change += dt
        self.check_status()

    def draw(self):
        if self.time_since_change < self.config.display_time:
            # Screen coords are -1 to 1 with 0 in the center, -1,-1 is bottom left.
            # text draw origin is at bottom left
            if self.config.halign == HAlignment.LEFT:
                x = -1 + self.config.x_margin
            elif self.config.halign == HAlignment.RIGHT:
                x = 1 - self._text.width - self.config.x_margin
            else:  # CENTER
                x = -self._text.width / 2

            if self.config.valign == VAlignment.BOTTOM:
                y = -1 + self.config.y_margin
            elif self.config.valign == VAlignment.TOP:
                y = 1 - self._text.height - self.config.y_margin
            else:  # CENTER
                y = -self._text.height / 2

            self._text.draw(x, y)


objects = []

window = create_window()

if CONFIG_FILE_PATH.exists():
    with open(CONFIG_FILE_PATH, "r") as f:
        config_dict = json.load(f)
        for obj in config_dict:
            if "type" not in obj:
                obj["type"] = "StatusDisplay"
            if obj["type"] == "StatusDisplay":
                del obj["type"]
                config = StatusDisplayConfig.model_validate(obj)
                osd = StatusDisplay(window, config)
                objects.append(osd)
            elif obj["type"] == "LogoDisplay":
                del obj["type"]
                config = LogoDisplayConfig.model_validate(obj)
                logo = LogoDisplay(window, config)
                objects.append(logo)
            elif obj["type"] == "HybridDisplay":
                del obj["type"]
                config_status = StatusDisplayConfig.model_validate(obj)
                config_logo = LogoDisplayConfig.model_validate(obj)
                status_osd = StatusDisplay(window, config_status)
                status_logo = LogoDisplay(window, config_logo)
                objects.append(logo)
                objects.append(osd)
            else:
                print(f"Unrecognized osd object type: {obj['type']}")

else:
    config = StatusDisplayConfig()
    objects.append(StatusDisplay(window, config))


# --------------------------
# Main loop

now = glfw.get_time()
while not glfw.window_should_close(window):
    glfw.wait_events_timeout(1.0 / 30.0)  # ~30 FPS, low CPU
    now, last = glfw.get_time(), now
    delta_time = now - last

    clear_screen()

    for obj in objects:
        obj.update(delta_time)

    # Draw objects with StatusDisplay on top
    for obj in sorted(objects, key=lambda x: isinstance(x, StatusDisplay)):
        obj.draw()

    glfw.swap_buffers(window)

# Cleanup
glfw.terminate()
