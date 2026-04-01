"""Import all models so Base.metadata registers them for create_all()."""

from jira_emulator.models.project import Project, ProjectIssueType, ProjectWorkflow  # noqa: F401
from jira_emulator.models.issue_type import IssueType  # noqa: F401
from jira_emulator.models.status import Status  # noqa: F401
from jira_emulator.models.priority import Priority  # noqa: F401
from jira_emulator.models.resolution import Resolution  # noqa: F401
from jira_emulator.models.user import User  # noqa: F401
from jira_emulator.models.api_token import ApiToken  # noqa: F401
from jira_emulator.models.issue import Issue, IssueSequence  # noqa: F401
from jira_emulator.models.comment import Comment  # noqa: F401
from jira_emulator.models.label import Label  # noqa: F401
from jira_emulator.models.component import Component, IssueComponent  # noqa: F401
from jira_emulator.models.version import Version, IssueFixVersion, IssueAffectsVersion  # noqa: F401
from jira_emulator.models.workflow import Workflow, WorkflowTransition  # noqa: F401
from jira_emulator.models.link import IssueLinkType, IssueLink  # noqa: F401
from jira_emulator.models.watcher import Watcher  # noqa: F401
from jira_emulator.models.custom_field import CustomField, IssueCustomFieldValue  # noqa: F401
from jira_emulator.models.sprint import Sprint, IssueSprint  # noqa: F401
