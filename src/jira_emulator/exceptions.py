"""Custom exception classes for the Jira Emulator."""


class JiraEmulatorError(Exception):
    """Base exception for all Jira Emulator errors."""
    pass


class IssueNotFoundError(JiraEmulatorError):
    """Raised when an issue is not found."""
    def __init__(self, key_or_id: str):
        self.key_or_id = key_or_id
        super().__init__(f"Issue Does Not Exist: {key_or_id}")


class ProjectNotFoundError(JiraEmulatorError):
    """Raised when a project is not found."""
    def __init__(self, key_or_id: str):
        self.key_or_id = key_or_id
        super().__init__(f"Project Does Not Exist: {key_or_id}")


class InvalidTransitionError(JiraEmulatorError):
    """Raised when a transition is invalid."""
    def __init__(self, transition_id: int):
        self.transition_id = transition_id
        super().__init__(f"Invalid transition {transition_id}")


class JQLParseError(JiraEmulatorError):
    """Raised when JQL parsing fails."""
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__(f"Error in the JQL Query: {detail}")
