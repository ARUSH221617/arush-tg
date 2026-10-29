import io
import time
import base64
from typing import Tuple, Dict, Any, Optional
from PIL import Image

try:
    import mss
    import pyautogui
    # Configure pyautogui safety
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
except ImportError:
    mss = None
    pyautogui = None

class WindowsComputerController:
    """
    Implements Anthropic's `computer_20241022` specification natively on Windows.
    Handles high-DPI scaling, mouse events, keyboard input, and screen captures.
    """

    def __init__(self, target_width: int = 1280, target_height: int = 800):
        self.target_width = target_width
        self.target_height = target_height
        self._sct = mss.mss() if mss else None

    def _get_primary_monitor(self) -> Dict[str, int]:
        if not self._sct:
            raise RuntimeError("mss is not installed or display is unavailable.")
        # monitor[1] is the primary monitor in mss
        return self._sct.monitors[1]

    def capture_screenshot(self) -> Tuple[Image.Image, str]:
        """
        Captures the primary monitor, downscales to target resolution,
        compresses as JPEG (quality=80) to minimize tokens, and returns
        both PIL.Image and base64 string.
        """
        mon = self._get_primary_monitor()
        raw = self._sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

        # Resize preserving target_width and target_height
        resized = img.resize((self.target_width, self.target_height), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        # Using JPEG with quality 80 yields small ~70KB payloads instead of 2MB PNGs
        resized.save(buffer, format="JPEG", quality=80, optimize=True)
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return resized, b64_data

    def _scale_coordinates(self, x: int, y: int) -> Tuple[int, int]:
        """Scales coordinates from Claude's target resolution to native display resolution."""
        mon = self._get_primary_monitor()
        native_w = mon["width"]
        native_h = mon["height"]

        real_x = int(x * (native_w / self.target_width)) + mon["left"]
        real_y = int(y * (native_h / self.target_height)) + mon["top"]
        return real_x, real_y

    def execute_action(
        self,
        action: str,
        coordinate: Optional[Tuple[int, int]] = None,
        text: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes an action following Anthropic's computer tool specification.
        """
        if not pyautogui:
            return {"error": "pyautogui is not installed"}

        try:
            if action == "screenshot":
                _, b64_img = self.capture_screenshot()
                return {
                    "status": "success",
                    "action": "screenshot",
                    "base64_image": b64_img
                }

            elif action == "mouse_move":
                if not coordinate:
                    return {"error": "coordinate required for mouse_move"}
                rx, ry = self._scale_coordinates(coordinate[0], coordinate[1])
                pyautogui.moveTo(rx, ry, duration=0.2)
                return {"status": "success", "action": "mouse_move", "to": [rx, ry]}

            elif action == "left_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1])
                    pyautogui.click(rx, ry)
                else:
                    pyautogui.click()
                return {"status": "success", "action": "left_click"}

            elif action == "right_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1])
                    pyautogui.rightClick(rx, ry)
                else:
                    pyautogui.rightClick()
                return {"status": "success", "action": "right_click"}

            elif action == "double_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1])
                    pyautogui.doubleClick(rx, ry)
                else:
                    pyautogui.doubleClick()
                return {"status": "success", "action": "double_click"}

            elif action == "triple_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1])
                    pyautogui.click(rx, ry, clicks=3, interval=0.1)
                else:
                    pyautogui.click(clicks=3, interval=0.1)
                return {"status": "success", "action": "triple_click"}

            elif action == "middle_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1])
                    pyautogui.middleClick(rx, ry)
                else:
                    pyautogui.middleClick()
                return {"status": "success", "action": "middle_click"}

            elif action == "type":
                if not text:
                    return {"error": "text required for type action"}
                pyautogui.write(text, interval=0.03)
                return {"status": "success", "action": "type", "text": text}

            elif action == "key":
                if not text:
                    return {"error": "text required for key combination (e.g. 'ctrl+c', 'enter', 'tab')"}
                keys = [k.strip().lower() for k in text.split("+")]
                if len(keys) == 1:
                    pyautogui.press(keys[0])
                else:
                    pyautogui.hotkey(*keys)
                return {"status": "success", "action": "key", "keys": keys}

            elif action == "cursor_position":
                cur_x, cur_y = pyautogui.position()
                mon = self._get_primary_monitor()
                # Scale back to model coordinate space
                mx = int((cur_x - mon["left"]) * (self.target_width / mon["width"]))
                my = int((cur_y - mon["top"]) * (self.target_height / mon["height"]))
                return {"status": "success", "coordinate": [mx, my]}

            else:
                return {"error": f"Unknown computer action: {action}"}

        except Exception as e:
            return {"error": f"Failed to execute computer action '{action}': {str(e)}"}

controller = WindowsComputerController()
