import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

BarWidget {
    id: root
    moduleName: "deepseek-2api"

    property string statusText: "󰚩"
    property color statusColor: "#ef4444"
    property string statusTooltip: "Deepseek-2api: проверка..."

    // Цвета статусов
    readonly property color colorActive:   "#10b981"
    readonly property color colorWarning:  "#f59e0b"
    readonly property color colorError:    "#ef4444"
    readonly property color colorCached:   "#f59e0b"

    Process {
        id: statusProc
        command: ["bash", "-lc",
                  "~/.config/omarchy/plugins/deepseek-2api/status.sh"]
        running: false

        stdout: SplitParser {
            onRead: function(line) {
                if (!line) return
                try {
                    var d = JSON.parse(line)

                    root.statusText    = d.text || "󰚩"
                    root.statusTooltip = d.tooltip || "Deepseek-2api"

                    // Если данные из кэша — всегда оранжевый,
                    // даже если в кэше был active.
                    if (d.cached === true) {
                        root.statusColor = root.colorCached
                    } else if (d.status === "active") {
                        root.statusColor = root.colorActive
                    } else if (d.status === "warning") {
                        root.statusColor = root.colorWarning
                    } else {
                        root.statusColor = root.colorError
                    }
                } catch (e) {
                    console.log("deepseek-2api: parse error", e)
                }
            }
        }
    }

    Timer {
        interval: 5000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: {
            if (!statusProc.running) {
                statusProc.running = true
            }
        }
    }

    implicitWidth: button.implicitWidth
    implicitHeight: button.implicitHeight

    BarIconButton {
        id: button
        anchors.fill: parent
        bar: root.bar
        text: root.statusText
        foreground: root.statusColor
        tooltipText: root.statusTooltip

        onPressed: function(b) {
            if (b === Qt.LeftButton) {
                Quickshell.execDetached([
                    "bash", "-lc",
                    "~/.config/omarchy/plugins/deepseek-2api/open-harness.sh"
                ])
            } else if (b === Qt.RightButton) {
                // Auto-detect terminal: xdg-terminal-exec -> omarchy-launch-terminal
                // -> foot -> kitty -> alacritty
                Quickshell.execDetached([
                    "bash", "-lc",
                    "if command -v xdg-terminal-exec >/dev/null 2>&1; then " +
                    "  xdg-terminal-exec journalctl --user -u deepseek-2api.service -f; " +
                    "elif command -v omarchy-launch-terminal >/dev/null 2>&1; then " +
                    "  omarchy-launch-terminal journalctl --user -u deepseek-2api.service -f; " +
                    "elif command -v foot >/dev/null 2>&1; then " +
                    "  foot journalctl --user -u deepseek-2api.service -f; " +
                    "elif command -v kitty >/dev/null 2>&1; then " +
                    "  kitty journalctl --user -u deepseek-2api.service -f; " +
                    "elif command -v alacritty >/dev/null 2>&1; then " +
                    "  alacritty -e journalctl --user -u deepseek-2api.service -f; " +
                    "else " +
                    "  notify-send 'DeepSeek 2API' 'Не найден ни один терминал'; " +
                    "fi"
                ])
            } else if (b === Qt.MiddleButton) {
                Quickshell.execDetached([
                    "bash", "-lc",
                    "systemctl --user restart deepseek-2api.service deepseek-harness.service"
                ])
            }
        }
    }
}
