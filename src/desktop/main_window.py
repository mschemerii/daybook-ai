from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from src.desktop.composition import DesktopServices, ShellSnapshot
from src.desktop.theme import AppearanceManager
from src.desktop.widgets import ContentCard, MetricCard
from src.desktop.views import (
    AssistantView,
    JournalView,
    ReportsView,
    TasksView,
    TodayView,
    about_view,
    ethical_ai_view,
)
from src.runtime.preferences import VALID_APPEARANCES


@dataclass(frozen=True, slots=True)
class NavigationDestination:
    key: str
    label: str


NAVIGATION_DESTINATIONS = (
    NavigationDestination("today", "Today"),
    NavigationDestination("tasks", "Tasks"),
    NavigationDestination("journal", "Journal"),
    NavigationDestination("reports", "Reports"),
    NavigationDestination("assistant", "Assistant"),
    NavigationDestination("ethical-ai", "Ethical AI"),
    NavigationDestination("about", "About"),
    NavigationDestination("settings", "Settings"),
)


class MainWindow(QMainWindow):
    """Native Daybook workspace backed by one shared application service graph."""

    closing = Signal()

    def __init__(
        self,
        services: DesktopServices,
        appearance: AppearanceManager,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.services = services
        self.appearance = appearance
        self._current_destination = "today"
        self._view_indexes: dict[str, int] = {}
        self._settings_appearance: QComboBox | None = None
        self.today_view: TodayView | None = None
        self.tasks_view: TasksView | None = None
        self.journal_view: JournalView | None = None
        self.reports_view: ReportsView | None = None
        self.assistant_view: AssistantView | None = None
        self._snapshot = services.shell_snapshot()

        self.setObjectName("daybookMainWindow")
        self.setWindowTitle("Daybook AI")
        self.resize(1360, 760)
        self.setMinimumSize(1000, 620)
        self.setStatusBar(QStatusBar(self))

        central = QWidget(self)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        layout.addWidget(self._build_workspace(), 1)
        self.setCentralWidget(central)

        self._build_status_bar()
        self.appearance.appearance_changed.connect(self._sync_appearance_control)
        self.navigate("today")

    @property
    def current_destination(self) -> str:
        return self._current_destination

    @property
    def navigation_keys(self) -> tuple[str, ...]:
        return tuple(destination.key for destination in NAVIGATION_DESTINATIONS)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame(self)
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(205)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 20, 18, 18)
        layout.setSpacing(12)

        brand = QLabel("Daybook AI")
        brand.setObjectName("brand")
        identity = QLabel("LOCAL-FIRST PRODUCTIVITY")
        identity.setObjectName("brandSubtle")

        self.navigation = QListWidget(sidebar)
        self.navigation.setObjectName("navigation")
        self.navigation.setAccessibleName("Daybook navigation")
        self.navigation.setSpacing(1)
        self.navigation.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        for destination in NAVIGATION_DESTINATIONS:
            item = QListWidgetItem(destination.label)
            item.setData(Qt.ItemDataRole.UserRole, destination.key)
            self.navigation.addItem(item)
        self.navigation.currentItemChanged.connect(self._navigation_changed)

        layout.addWidget(brand)
        layout.addWidget(identity)
        layout.addSpacing(10)
        layout.addWidget(self.navigation, 1)

        principle = QLabel(
            "Rules determine.\nAI explains and proposes.\nHumans approve."
        )
        principle.setObjectName("brandSubtle")
        principle.setWordWrap(True)
        layout.addWidget(principle)
        return sidebar

    def _build_workspace(self) -> QWidget:
        workspace = QWidget(self)
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(28, 24, 28, 18)
        layout.setSpacing(16)

        self.page_title = QLabel()
        self.page_title.setObjectName("pageTitle")
        self.page_subtitle = QLabel()
        self.page_subtitle.setObjectName("pageSubtitle")
        self.page_subtitle.setWordWrap(True)

        self.stack = QStackedWidget(workspace)
        self.stack.setObjectName("workspaceStack")
        self.stack.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )

        if hasattr(self.services, "task_service"):
            self.today_view = TodayView(self.services, self)
            self.tasks_view = TasksView(self.services, self)
            self.journal_view = JournalView(self.services, self)
            self.reports_view = ReportsView(self.services, self)
            self.assistant_view = AssistantView(
                self.services, self._snapshot.ai_status, self
            )
            self.today_view.open_task_requested.connect(self.open_task)
            self.today_view.journal_requested.connect(lambda: self.navigate("journal"))
            self.tasks_view.changed.connect(self._refresh_data_views)
            self.journal_view.changed.connect(self._refresh_data_views)
            views = {
                "today": self.today_view,
                "tasks": self.tasks_view,
                "journal": self.journal_view,
                "reports": self.reports_view,
                "assistant": self.assistant_view,
                "ethical-ai": ethical_ai_view(self),
                "about": about_view(self),
                "settings": self._settings_view(),
            }
        else:
            # Lightweight Phase 9A fakes remain useful for shell-only tests.
            views = {
                "today": self._build_today_view(self._snapshot),
                "tasks": self._placeholder_view(
                    "Tasks", "Native task workflows use Daybook application services."
                ),
                "journal": self._placeholder_view(
                    "Journal",
                    "Native journal workflows use Daybook SQLite persistence.",
                ),
                "reports": self._placeholder_view(
                    "Reports", "Native reports reuse deterministic report calculations."
                ),
                "assistant": self._assistant_view(self._snapshot),
                "ethical-ai": self._ethical_ai_view(),
                "about": self._about_view(),
                "settings": self._settings_view(),
            }
        for destination in NAVIGATION_DESTINATIONS:
            index = self.stack.addWidget(views[destination.key])
            self._view_indexes[destination.key] = index

        layout.addWidget(self.page_title)
        layout.addWidget(self.page_subtitle)
        layout.addWidget(self.stack, 1)
        return workspace

    def _build_today_view(self, snapshot: ShellSnapshot) -> QWidget:
        view = QWidget(self)
        view.setObjectName("todayView")
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(18)

        intro = ContentCard(
            "Start your day with clarity.",
            "This Phase 9A dashboard is intentionally read-only. It proves the "
            "native shell can reach Daybook's existing SQLite repositories and "
            "services directly.",
        )
        layout.addWidget(intro)

        metrics = QGridLayout()
        metrics.setHorizontalSpacing(10)
        metrics.setVerticalSpacing(10)
        metrics.addWidget(MetricCard("Open tasks", str(snapshot.open_tasks)), 0, 0)
        metrics.addWidget(MetricCard("Due today", str(snapshot.due_today)), 0, 1)
        metrics.addWidget(MetricCard("Completed", str(snapshot.completed_tasks)), 0, 2)
        metrics.addWidget(
            MetricCard(
                "Journal today",
                "Recorded" if snapshot.journal_today else "Not recorded",
            ),
            0,
            3,
        )
        layout.addLayout(metrics)

        service_text = (
            f"Database: {snapshot.database_name}. Local AI: {snapshot.ai_status}. "
            "No model call is made while constructing or navigating the desktop shell."
        )
        layout.addWidget(ContentCard("Service connection", service_text))
        layout.addStretch(1)
        return view

    def _assistant_view(self, snapshot: ShellSnapshot) -> QWidget:
        if snapshot.ai_status == "Unavailable":
            body = (
                "The local model is unavailable. Deterministic task, journal, and "
                "reporting services remain usable. "
                "Assistant workflows migrate in Phase 9B."
            )
        elif snapshot.ai_status == "Ready":
            body = (
                "The local model runtime is ready. This foundation shell deliberately "
                "makes no inference request; bounded assistant workflows migrate in "
                "Phase 9B."
            )
        else:
            body = (
                "The local model has not been verified in this process. The desktop "
                "shell remains usable without inference."
            )
        return self._placeholder_view("Assistant", body)

    def _ethical_ai_view(self) -> QWidget:
        return self._placeholder_view(
            "Ethical AI",
            "Rules determine. AI explains. AI proposes. Humans approve. The native "
            "presentation layer does not change Daybook's deterministic authority "
            "or human-approval boundaries.",
        )

    def _about_view(self) -> QWidget:
        return self._placeholder_view(
            "About Daybook AI",
            "Daybook AI is a local-first task manager, daily journal, deterministic "
            "reporting system, and bounded local AI assistant. Phase 9A adds the "
            "native PySide6 foundation without removing Streamlit yet.",
        )

    def _settings_view(self) -> QWidget:
        view = QWidget(self)
        view.setObjectName("settingsView")
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(14)

        card = QFrame(view)
        card.setObjectName("contentCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(8)
        title = QLabel("Appearance")
        title.setStyleSheet("font-weight: 600;")
        hint = QLabel(
            "Choose a light or dark native appearance. This preference is shared "
            "with the existing Daybook preference file."
        )
        hint.setObjectName("mutedText")
        hint.setWordWrap(True)
        combo = QComboBox(card)
        combo.setObjectName("appearanceCombo")
        combo.setAccessibleName("Appearance")
        combo.addItems(list(VALID_APPEARANCES))
        combo.setCurrentText(self.appearance.appearance)
        combo.currentTextChanged.connect(self.appearance.set_appearance)
        self._settings_appearance = combo

        card_layout.addWidget(title)
        card_layout.addWidget(hint)
        card_layout.addWidget(combo)
        layout.addWidget(card)
        layout.addWidget(
            ContentCard(
                "Preference scope",
                "Appearance remains the only general desktop preference. Report "
                "fiscal settings stay with the reporting workflow.",
            )
        )
        layout.addStretch(1)
        return view

    def _placeholder_view(self, title: str, body: str) -> QWidget:
        view = QWidget(self)
        view.setObjectName(f"{title.lower().replace(' ', '').replace('-', '')}View")
        layout = QVBoxLayout(view)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addWidget(ContentCard(title, body))
        layout.addStretch(1)
        return view

    def _build_status_bar(self) -> None:
        self.status_message = QLabel("Ready")
        self.status_message.setObjectName("statusMessage")
        if self._snapshot.ai_status == "Unavailable":
            ai_text = "Local AI unavailable · deterministic features remain available"
        else:
            ai_text = f"Local AI: {self._snapshot.ai_status}"
        self.ai_status = QLabel(ai_text)
        self.ai_status.setObjectName("aiStatus")
        self.statusBar().addWidget(self.status_message, 1)
        self.statusBar().addPermanentWidget(self.ai_status)

    def navigate(self, key: str) -> None:
        if key not in self._view_indexes:
            raise ValueError(f"Unknown desktop destination: {key}")
        for row in range(self.navigation.count()):
            item = self.navigation.item(row)
            if item.data(Qt.ItemDataRole.UserRole) == key:
                if self.navigation.currentRow() != row:
                    self.navigation.setCurrentRow(row)
                else:
                    self._select_destination(key)
                return
        raise ValueError(f"Navigation destination is not registered: {key}")

    def _navigation_changed(
        self,
        current: QListWidgetItem | None,
        previous: QListWidgetItem | None,
    ) -> None:
        del previous
        if current is None:
            return
        self._select_destination(str(current.data(Qt.ItemDataRole.UserRole)))

    def _select_destination(self, key: str) -> None:
        index = self._view_indexes[key]
        destination = next(item for item in NAVIGATION_DESTINATIONS if item.key == key)
        self._current_destination = key
        self.stack.setCurrentIndex(index)
        self.page_title.setText(destination.label)
        self.page_subtitle.setText(self._subtitle_for(key))
        self.status_message.setText(f"Viewing {destination.label}")
        if key == "today" and self.today_view is not None:
            self.today_view.refresh()
        elif key == "tasks" and self.tasks_view is not None:
            self.tasks_view.refresh()
        elif key == "journal" and self.journal_view is not None:
            self.journal_view.load()

    @staticmethod
    def _subtitle_for(key: str) -> str:
        subtitles = {
            "today": "Deterministic focus, due work, blockers, completion, and journal status.",
            "tasks": "Create, update, organize, track, and complete locally stored work.",
            "journal": "Record progress, blockers, and reflection by calendar date.",
            "reports": "Deterministic task and time aggregation with native export controls.",
            "assistant": "Bounded local AI remains optional and non-authoritative.",
            "ethical-ai": (
                "Daybook's governance principle remains unchanged by the desktop "
                "transition."
            ),
            "about": "Local-first architecture, deterministic rules, and bounded AI.",
            "settings": "Desktop shell preferences and application configuration.",
        }
        return subtitles[key]

    def open_task(self, task_id: int) -> None:
        if self.tasks_view is None:
            return
        self.navigate("tasks")
        self.tasks_view.open_task(task_id)

    def _refresh_data_views(self) -> None:
        self._snapshot = self.services.shell_snapshot()
        if self.today_view is not None:
            self.today_view.refresh()

    def _sync_appearance_control(self, appearance: str) -> None:
        if self._settings_appearance is None:
            return
        blocker = QSignalBlocker(self._settings_appearance)
        self._settings_appearance.setCurrentText(appearance)
        del blocker

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.closing.emit()
        super().closeEvent(event)
