"""Base Huawei VRP driver abstraction (Target Architecture §3)."""
from abc import ABC
from typing import List, Optional, Any
from backend.app.devices.errors import check_vrp_banner_errors, ConfigRejected


class BaseVRPDriver(ABC):
    """Abstract driver providing Huawei VRP CLI mechanics and safety checks."""

    os_family: str = "base"
    netmiko_device_type: str = "huawei"
    commit_required: bool = False
    paging_disable_commands: List[str] = [
        "screen-length 0 temporary",
        "undo terminal monitor",
    ]
    enter_system_view_command: str = "system-view"
    exit_system_view_command: str = "return"

    def disable_paging(self, conn: Any) -> None:
        """Send commands to disable CLI output pagination."""
        for cmd in self.paging_disable_commands:
            try:
                conn.send_command(cmd)
            except Exception:
                pass

    def enter_system_view(self, conn: Any) -> str:
        """Enter configuration / system-view."""
        out = conn.send_command(self.enter_system_view_command)
        err = self.check_error(out)
        if err:
            raise ConfigRejected(f"Failed to enter system view: {err}", error_banner=err)
        return out

    def exit_system_view(self, conn: Any) -> str:
        """Exit back to user view."""
        return conn.send_command(self.exit_system_view_command)

    def check_error(self, output: str) -> Optional[str]:
        """Check for Huawei VRP error banners (Error:, Unrecognized command, etc.)."""
        return check_vrp_banner_errors(output)

    def commit(self, conn: Any) -> str:
        """Commit candidate configuration if required by OS family."""
        if not self.commit_required:
            return ""
        out = conn.send_command("commit")
        err = self.check_error(out)
        if err:
            raise ConfigRejected(f"Commit failed on {self.os_family}: {err}", command="commit", error_banner=err)
        return out
