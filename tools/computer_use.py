import io
import time
import uuid
import base64
from typing import Tuple, Dict, Any, Optional, List, Callable, Awaitable
from PIL import Image

try:
    import mss
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
except Exception:
    mss = None
    pyautogui = None


SENSITIVE_KEY_COMBOS = {"alt+f4", "ctrl+alt+del", "ctrl+shift+esc", "win+r"}
SENSITIVE_ACTIONS = {"kill_process", "delete_file", "system_shutdown"}


class PendingConfirmationManager:
    """
    Phase 4.1: Manages interactive Telegram confirmation buttons (`[Confirm Kill Task]`, `[Cancel]`)
    for sensitive PC/OS actions before they are executed.
    """

    def __init__(self):
        self._pending: Dict[str, Dict[str, Any]] = {}

    def create_pending_action(
        self,
        action_type: str,
        description: str,
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        action_id = uuid.uuid4().hex[:10]
        record = {
            "action_id": action_id,
            "action_type": action_type,
            "description": description,
            "payload": payload,
            "status": "pending",
            "created_at": time.time()
        }
        self._pending[action_id] = record
        return record

    def get_pending(self, action_id: str) -> Optional[Dict[str, Any]]:
        return self._pending.get(action_id)

    def resolve_pending(self, action_id: str, approved: bool) -> Optional[Dict[str, Any]]:
        rec = self._pending.get(action_id)
        if not rec:
            return None
        rec["status"] = "approved" if approved else "cancelled"
        return rec

    def list_pending(self) -> List[Dict[str, Any]]:
        return [v for v in self._pending.values() if v["status"] == "pending"]

    def cancel_all_pending(self) -> int:
        """Cancels all active pending confirmation requests and returns the number cancelled."""
        count = 0
        for rec in self._pending.values():
            if rec["status"] == "pending":
                rec["status"] = "cancelled"
                count += 1
        return count


confirmation_manager = PendingConfirmationManager()


class WindowsComputerController:
    """
    Phase 1 & Phase 4.1: Visual Computer Use (Sense-Decide-Act).
    Implements Anthropic/OpenAI computer control on Windows with:
    - Multi-monitor & high-DPI coordinate mapping
    - Mouse moves, clicks (left, right, double, triple, middle), drag, scroll
    - Keyboard typing & hotkeys
    - Interactive confirmation gate for sensitive actions
    """

    def __init__(self, target_width: int = 1280, target_height: int = 800):
        self.target_width = target_width
        self.target_height = target_height
        try:
            self._sct = mss.mss() if mss else None
        except Exception:
            self._sct = None

    def list_monitors(self) -> List[Dict[str, int]]:
        if not self._sct:
            # Provide synthetic primary monitor geometry in headless/container test environments
            return [{"left": 0, "top": 0, "width": 1920, "height": 1080}]
        return list(self._sct.monitors[1:])

    def _get_monitor(self, monitor_index: int = 1) -> Dict[str, int]:
        if not self._sct:
            return {"left": 0, "top": 0, "width": 1920, "height": 1080}
        monitors = self._sct.monitors
        if 1 <= monitor_index < len(monitors):
            return monitors[monitor_index]
        return monitors[1]

    def capture_screenshot(self, monitor_index: int = 1) -> Tuple[Image.Image, str]:
        """
        Captures the specified monitor, downscales to target resolution (1280x800),
        compresses as JPEG (quality=80) to minimize tokens (~70KB), and returns
        both PIL.Image and base64 string.
        """
        if not self._sct:
            # Headless fallback image for Docker/CI environments without an X11/Windows display
            img = Image.new("RGB", (self.target_width, self.target_height), color=(24, 28, 36))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=80)
            return img, base64.b64encode(buf.getvalue()).decode("utf-8")

        mon = self._get_monitor(monitor_index)
        raw = self._sct.grab(mon)
        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        resized = img.resize((self.target_width, self.target_height), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        resized.save(buffer, format="JPEG", quality=80, optimize=True)
        b64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return resized, b64_data

    def _scale_coordinates(self, x: int, y: int, monitor_index: int = 1) -> Tuple[int, int]:
        """Scales coordinates from vision model target resolution (1280x800) to native display resolution."""
        mon = self._get_monitor(monitor_index)
        native_w = mon["width"]
        native_h = mon["height"]

        clamped_x = max(0, min(self.target_width, int(x)))
        clamped_y = max(0, min(self.target_height, int(y)))

        real_x = int(round(clamped_x * (native_w / self.target_width))) + mon["left"]
        real_y = int(round(clamped_y * (native_h / self.target_height))) + mon["top"]
        return real_x, real_y

    def is_sensitive_action(self, action: str, text: Optional[str] = None) -> bool:
        if action in SENSITIVE_ACTIONS:
            return True
        if action == "key" and text and text.strip().lower() in SENSITIVE_KEY_COMBOS:
            return True
        return False

    def execute_action(
        self,
        action: str,
        coordinate: Optional[Tuple[int, int]] = None,
        text: Optional[str] = None,
        monitor_index: int = 1,
        scroll_amount: int = -3,
        require_confirmation_if_sensitive: bool = True,
        confirmed: bool = False
    ) -> Dict[str, Any]:
        """
        Executes a Sense-Decide-Act desktop action.
        If the action is sensitive and `confirmed=False`, creates a pending confirmation
        request for Telegram inline buttons (`[Confirm]`, `[Cancel]`).
        """
        if require_confirmation_if_sensitive and not confirmed and self.is_sensitive_action(action, text):
            pending = confirmation_manager.create_pending_action(
                action_type="computer",
                description=f"Computer action '{action}' with parameter '{text or coordinate}'",
                payload={
                    "action": action,
                    "coordinate": list(coordinate) if coordinate else None,
                    "text": text,
                    "monitor_index": monitor_index
                }
            )
            return {
                "status": "requires_confirmation",
                "action_id": pending["action_id"],
                "description": pending["description"],
                "inline_buttons": [
                    {"text": "✅ Confirm Action", "callback_data": f"confirm_action:{pending['action_id']}"},
                    {"text": "❌ Cancel", "callback_data": f"cancel_action:{pending['action_id']}"}
                ]
            }

        if action == "screenshot":
            _, b64_img = self.capture_screenshot(monitor_index=monitor_index)
            return {
                "status": "success",
                "action": "screenshot",
                "monitor": monitor_index,
                "base64_image": b64_img
            }

        if not pyautogui:
            # In headless/CI mode, return simulated coordinate mapping verification
            if coordinate:
                rx, ry = self._scale_coordinates(coordinate[0], coordinate[1], monitor_index)
                return {
                    "status": "simulated_headless",
                    "action": action,
                    "scaled_coordinate": [rx, ry],
                    "text": text
                }
            return {"error": "pyautogui is not installed or display unavailable"}

        try:
            if action == "mouse_move":
                if not coordinate:
                    return {"error": "coordinate required for mouse_move"}
                rx, ry = self._scale_coordinates(coordinate[0], coordinate[1], monitor_index)
                pyautogui.moveTo(rx, ry, duration=0.2)
                return {"status": "success", "action": "mouse_move", "to": [rx, ry]}

            elif action == "left_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1], monitor_index)
                    pyautogui.click(rx, ry)
                else:
                    pyautogui.click()
                return {"status": "success", "action": "left_click"}

            elif action == "right_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1], monitor_index)
                    pyautogui.rightClick(rx, ry)
                else:
                    pyautogui.rightClick()
                return {"status": "success", "action": "right_click"}

            elif action == "double_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1], monitor_index)
                    pyautogui.doubleClick(rx, ry)
                else:
                    pyautogui.doubleClick()
                return {"status": "success", "action": "double_click"}

            elif action == "triple_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1], monitor_index)
                    pyautogui.click(rx, ry, clicks=3, interval=0.1)
                else:
                    pyautogui.click(clicks=3, interval=0.1)
                return {"status": "success", "action": "triple_click"}

            elif action == "middle_click":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1], monitor_index)
                    pyautogui.middleClick(rx, ry)
                else:
                    pyautogui.middleClick()
                return {"status": "success", "action": "middle_click"}

            elif action == "scroll":
                if coordinate:
                    rx, ry = self._scale_coordinates(coordinate[0], coordinate[1], monitor_index)
                    pyautogui.moveTo(rx, ry, duration=0.1)
                pyautogui.scroll(scroll_amount)
                return {"status": "success", "action": "scroll", "scroll_amount": scroll_amount}

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
                mon = self._get_monitor(monitor_index)
                mx = int((cur_x - mon["left"]) * (self.target_width / mon["width"]))
                my = int((cur_y - mon["top"]) * (self.target_height / mon["height"]))
                return {"status": "success", "coordinate": [mx, my]}

            else:
                return {"error": f"Unknown computer action: {action}"}

        except Exception as e:
            return {"error": f"Failed to execute computer action '{action}': {str(e)}"}


controller = WindowsComputerController()
