# jira-emulator Enhancement Specification

**Complete technical specification for adding field metadata and status/workflow support**

---

## Executive Summary

This specification defines enhancements to jira-emulator to support:
1. Custom field metadata (required_for, allowed_values, available_for)
2. Status and workflow APIs (project/issue-type specific)
3. Configuration import system (JSON-based)

**Goals:**
- Match real JIRA REST API v2 behavior
- Enable realistic field validation and status workflows
- Provide import/export capabilities for configuration
- Remain database-agnostic (SQLite for testing, PostgreSQL for production)

**Non-Goals:**
- JIRA v3 API support (v2 only)
- Integration with specific tools (import format is generic)
- Production-level workflow engine (simplified for testing)
- Backward compatibility with existing installations
- Data migration from older versions

---

## 1. Database Schema

### 1.1 CustomField Table Enhancement

**Updated `custom_fields` table schema:**

```sql
CREATE TABLE custom_fields (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    field_id VARCHAR(50) UNIQUE NOT NULL,        -- e.g., "customfield_10001"
    name VARCHAR(100) NOT NULL,
    field_type VARCHAR(50) NOT NULL,
    description TEXT,
    -- NEW: Field validation metadata
    required_for JSON DEFAULT '[]',              -- ["Bug", "Task"]
    allowed_values JSON DEFAULT '[]',            -- ["High", "Medium", "Low"]
    available_for JSON DEFAULT '[]',             -- ["Bug", "Story", "Task"]
    schema_type VARCHAR(50),                     -- "string", "option", "array"
    schema_custom VARCHAR(100)                   -- Full JIRA custom type
);
```

**Python model:**

```python
# src/jira_emulator/models/custom_field.py
from sqlalchemy import Column, Integer, String, Text, JSON
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class CustomField(Base):
    __tablename__ = "custom_fields"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    field_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    field_type = Column(String(50), nullable=False)
    description = Column(Text)
    
    # Field validation metadata
    required_for = Column(JSON, default=list)      # Issue types requiring field
    allowed_values = Column(JSON, default=list)    # Valid dropdown values
    available_for = Column(JSON, default=list)     # Issue types that can use field
    schema_type = Column(String(50))               # JIRA schema type
    schema_custom = Column(String(100))            # Custom schema identifier
```

### 1.2 Status Table

**New `statuses` table:**

```sql
CREATE TABLE statuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status_id VARCHAR(50) UNIQUE NOT NULL,      -- e.g., "1", "10000"
    name VARCHAR(100) NOT NULL,                  -- e.g., "To Do", "In Progress"
    description TEXT,
    status_category VARCHAR(50) NOT NULL,        -- "new", "indeterminate", "done"
    icon_url VARCHAR(255)
);
```

**Python model:**

```python
# src/jira_emulator/models/status.py
class Status(Base):
    __tablename__ = "statuses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    status_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    status_category = Column(String(50), nullable=False)  # new/indeterminate/done
    icon_url = Column(String(255))
```

### 1.3 Workflow Tables

**New `workflows` and `workflow_statuses` tables:**

```sql
CREATE TABLE workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT
);

CREATE TABLE workflow_statuses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workflow_id INTEGER NOT NULL,
    status_id INTEGER NOT NULL,
    sequence INTEGER NOT NULL,  -- Order in workflow
    FOREIGN KEY (workflow_id) REFERENCES workflows(id),
    FOREIGN KEY (status_id) REFERENCES statuses(id),
    UNIQUE(workflow_id, status_id)
);
```

**Python models:**

```python
# src/jira_emulator/models/workflow.py
class Workflow(Base):
    __tablename__ = "workflows"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)

class WorkflowStatus(Base):
    __tablename__ = "workflow_statuses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
    status_id = Column(Integer, ForeignKey("statuses.id"), nullable=False)
    sequence = Column(Integer, nullable=False)
```

### 1.4 Project-Workflow Association

**New `project_workflows` table:**

```sql
CREATE TABLE project_workflows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    issue_type_id INTEGER NOT NULL,
    workflow_id INTEGER NOT NULL,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (issue_type_id) REFERENCES issue_types(id),
    FOREIGN KEY (workflow_id) REFERENCES workflows(id),
    UNIQUE(project_id, issue_type_id)
);
```

**Python model:**

```python
# src/jira_emulator/models/project_workflow.py
class ProjectWorkflow(Base):
    __tablename__ = "project_workflows"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    issue_type_id = Column(Integer, ForeignKey("issue_types.id"), nullable=False)
    workflow_id = Column(Integer, ForeignKey("workflows.id"), nullable=False)
```

---

## 2. REST API v2 Enhancements

### 2.1 Field Metadata API

**Enhanced GET /rest/api/2/field**

Return all fields including custom field metadata.

**Response format:**

```json
[
  {
    "id": "customfield_10001",
    "name": "Story Points",
    "custom": true,
    "orderable": true,
    "navigable": true,
    "searchable": true,
    "clauseNames": ["cf[10001]", "Story Points"],
    "schema": {
      "type": "number",
      "custom": "com.atlassian.jira.plugin.system.customfieldtypes:float",
      "customId": 10001
    },
    "required_for": ["Story", "Epic"],
    "allowed_values": [],
    "available_for": ["Story", "Epic", "Task"]
  },
  {
    "id": "customfield_10002",
    "name": "Team",
    "custom": true,
    "schema": {
      "type": "option",
      "custom": "com.atlassian.jira.plugin.system.customfieldtypes:select"
    },
    "required_for": [],
    "allowed_values": ["Platform", "SaaS", "Cloud", "AI"],
    "available_for": ["Bug", "Story", "Task", "Epic"]
  }
]
```

**Implementation:**

```python
# src/jira_emulator/routers/fields.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.custom_field import CustomField

router = APIRouter()

@router.get("/rest/api/2/field")
async def get_fields(db: Session = Depends(get_db)):
    """Get all fields including custom field metadata."""
    
    # System fields (always present)
    fields = [
        {
            "id": "summary",
            "name": "Summary",
            "custom": False,
            "orderable": True,
            "navigable": True,
            "searchable": True,
            "schema": {"type": "string", "system": "summary"}
        },
        {
            "id": "issuetype",
            "name": "Issue Type",
            "custom": False,
            "schema": {"type": "issuetype", "system": "issuetype"}
        },
        {
            "id": "status",
            "name": "Status",
            "custom": False,
            "schema": {"type": "status", "system": "status"}
        },
        {
            "id": "priority",
            "name": "Priority",
            "custom": False,
            "schema": {"type": "priority", "system": "priority"}
        }
        # ... add all standard JIRA fields
    ]
    
    # Custom fields from database
    custom_fields = db.query(CustomField).all()
    
    for cf in custom_fields:
        field_data = {
            "id": cf.field_id,
            "name": cf.name,
            "custom": True,
            "orderable": True,
            "navigable": True,
            "searchable": True,
            "clauseNames": [f"cf[{cf.field_id.replace('customfield_', '')}]", cf.name],
            "schema": {
                "type": cf.schema_type or cf.field_type,
                "custom": cf.schema_custom,
                "customId": int(cf.field_id.replace("customfield_", ""))
            },
            "required_for": cf.required_for or [],
            "allowed_values": cf.allowed_values or [],
            "available_for": cf.available_for or []
        }
        fields.append(field_data)
    
    return fields
```

### 2.2 Status API

**GET /rest/api/2/status**

List all available statuses.

**Response format:**

```json
[
  {
    "self": "http://localhost:8080/rest/api/2/status/1",
    "description": "The issue is open and ready for work.",
    "iconUrl": "http://localhost:8080/images/icons/statuses/open.png",
    "name": "To Do",
    "id": "1",
    "statusCategory": {
      "self": "http://localhost:8080/rest/api/2/statuscategory/2",
      "id": 2,
      "key": "new",
      "colorName": "blue-gray",
      "name": "To Do"
    }
  },
  {
    "id": "3",
    "name": "In Progress",
    "statusCategory": {
      "id": 4,
      "key": "indeterminate",
      "name": "In Progress"
    }
  },
  {
    "id": "10000",
    "name": "Done",
    "statusCategory": {
      "id": 3,
      "key": "done",
      "name": "Done"
    }
  }
]
```

**Implementation:**

```python
# src/jira_emulator/routers/status.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from ..database import get_db
from ..models.status import Status

router = APIRouter()

STATUS_CATEGORIES = {
    "new": {"id": 2, "key": "new", "colorName": "blue-gray", "name": "To Do"},
    "indeterminate": {"id": 4, "key": "indeterminate", "colorName": "yellow", "name": "In Progress"},
    "done": {"id": 3, "key": "done", "colorName": "green", "name": "Done"}
}

@router.get("/rest/api/2/status")
async def get_statuses(db: Session = Depends(get_db)):
    """Get all statuses."""
    statuses = db.query(Status).all()
    
    result = []
    for status in statuses:
        category = STATUS_CATEGORIES.get(status.status_category, STATUS_CATEGORIES["indeterminate"])
        
        result.append({
            "self": f"http://localhost:8080/rest/api/2/status/{status.status_id}",
            "description": status.description or "",
            "iconUrl": status.icon_url or f"http://localhost:8080/images/icons/statuses/{status.status_category}.png",
            "name": status.name,
            "id": status.status_id,
            "statusCategory": {
                "self": f"http://localhost:8080/rest/api/2/statuscategory/{category['id']}",
                "id": category["id"],
                "key": category["key"],
                "colorName": category["colorName"],
                "name": category["name"]
            }
        })
    
    return result

@router.get("/rest/api/2/status/{status_id}")
async def get_status(status_id: str, db: Session = Depends(get_db)):
    """Get single status by ID."""
    status = db.query(Status).filter(Status.status_id == status_id).first()
    if not status:
        raise HTTPException(status_code=404, detail="Status not found")
    
    category = STATUS_CATEGORIES.get(status.status_category, STATUS_CATEGORIES["indeterminate"])
    
    return {
        "self": f"http://localhost:8080/rest/api/2/status/{status.status_id}",
        "description": status.description or "",
        "iconUrl": status.icon_url or f"http://localhost:8080/images/icons/statuses/{status.status_category}.png",
        "name": status.name,
        "id": status.status_id,
        "statusCategory": category
    }
```

### 2.3 Project API Enhancement

**Enhanced GET /rest/api/2/project/{projectKey}**

Include issue types with their available statuses.

**Response format:**

```json
{
  "self": "http://localhost:8080/rest/api/2/project/PROJ",
  "id": "10000",
  "key": "PROJ",
  "name": "Project Name",
  "issueTypes": [
    {
      "self": "http://localhost:8080/rest/api/2/issuetype/1",
      "id": "1",
      "name": "Bug",
      "subtask": false,
      "statuses": [
        {
          "id": "1",
          "name": "To Do",
          "statusCategory": {"key": "new"}
        },
        {
          "id": "3",
          "name": "In Progress",
          "statusCategory": {"key": "indeterminate"}
        },
        {
          "id": "10000",
          "name": "Done",
          "statusCategory": {"key": "done"}
        }
      ]
    }
  ]
}
```

**Implementation:**

```python
# src/jira_emulator/routers/projects.py
@router.get("/rest/api/2/project/{project_key}")
async def get_project(project_key: str, db: Session = Depends(get_db)):
    """Get project with issue types and statuses."""
    from ..models.project import Project
    from ..models.issue_type import IssueType
    from ..models.project_workflow import ProjectWorkflow
    from ..models.workflow import Workflow, WorkflowStatus
    from ..models.status import Status
    
    project = db.query(Project).filter(Project.key == project_key).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    issue_types = db.query(IssueType).all()
    issue_types_data = []
    
    for issue_type in issue_types:
        # Get workflow for this project + issue type
        project_workflow = db.query(ProjectWorkflow).filter(
            ProjectWorkflow.project_id == project.id,
            ProjectWorkflow.issue_type_id == issue_type.id
        ).first()
        
        statuses = []
        if project_workflow:
            # Get statuses from workflow
            workflow_statuses = db.query(WorkflowStatus, Status).join(
                Status, WorkflowStatus.status_id == Status.id
            ).filter(
                WorkflowStatus.workflow_id == project_workflow.workflow_id
            ).order_by(WorkflowStatus.sequence).all()
            
            for ws, status in workflow_statuses:
                category = STATUS_CATEGORIES.get(status.status_category, STATUS_CATEGORIES["indeterminate"])
                statuses.append({
                    "id": status.status_id,
                    "name": status.name,
                    "statusCategory": {"key": category["key"]}
                })
        
        issue_types_data.append({
            "self": f"http://localhost:8080/rest/api/2/issuetype/{issue_type.id}",
            "id": str(issue_type.id),
            "name": issue_type.name,
            "subtask": issue_type.subtask or False,
            "statuses": statuses
        })
    
    return {
        "self": f"http://localhost:8080/rest/api/2/project/{project.key}",
        "id": str(project.id),
        "key": project.key,
        "name": project.name,
        "issueTypes": issue_types_data
    }
```

### 2.4 Create Metadata API

**GET /rest/api/2/issue/createmeta**

Return field metadata for creating issues.

**Query parameters:**
- `projectKeys` - Project key(s) to get metadata for
- `issuetypeNames` - Issue type name(s) to filter by
- `expand` - Additional data to include

**Response format:**

```json
{
  "expand": "projects",
  "projects": [
    {
      "self": "http://localhost:8080/rest/api/2/project/PROJ",
      "id": "10000",
      "key": "PROJ",
      "name": "Project Name",
      "issuetypes": [
        {
          "self": "http://localhost:8080/rest/api/2/issuetype/1",
          "id": "1",
          "name": "Bug",
          "fields": {
            "summary": {
              "required": true,
              "schema": {"type": "string"},
              "name": "Summary"
            },
            "customfield_10002": {
              "required": true,
              "schema": {"type": "option"},
              "name": "Team",
              "allowedValues": [
                {"value": "Platform"},
                {"value": "SaaS"}
              ]
            }
          }
        }
      ]
    }
  ]
}
```

**Implementation:**

```python
# src/jira_emulator/routers/issues.py
@router.get("/rest/api/2/issue/createmeta")
async def get_create_metadata(
    projectKeys: str = None,
    issuetypeNames: str = None,
    expand: str = None,
    db: Session = Depends(get_db)
):
    """Get metadata for creating issues."""
    from ..models.project import Project
    from ..models.issue_type import IssueType
    from ..models.custom_field import CustomField
    
    # Filter projects
    projects_query = db.query(Project)
    if projectKeys:
        keys = [k.strip() for k in projectKeys.split(",")]
        projects_query = projects_query.filter(Project.key.in_(keys))
    projects = projects_query.all()
    
    # Filter issue types
    issuetypes_query = db.query(IssueType)
    if issuetypeNames:
        names = [n.strip() for n in issuetypeNames.split(",")]
        issuetypes_query = issuetypes_query.filter(IssueType.name.in_(names))
    issue_types = issuetypes_query.all()
    
    # Get all custom fields
    custom_fields = db.query(CustomField).all()
    
    projects_data = []
    for project in projects:
        issuetypes_data = []
        
        for issue_type in issue_types:
            # Build fields object
            fields = {
                "summary": {
                    "required": True,
                    "schema": {"type": "string", "system": "summary"},
                    "name": "Summary"
                },
                "issuetype": {
                    "required": True,
                    "schema": {"type": "issuetype", "system": "issuetype"},
                    "name": "Issue Type"
                },
                "priority": {
                    "required": False,
                    "schema": {"type": "priority", "system": "priority"},
                    "name": "Priority"
                }
            }
            
            # Add custom fields
            for cf in custom_fields:
                # Check if field is available for this issue type
                if cf.available_for and issue_type.name not in cf.available_for:
                    continue
                
                field_def = {
                    "required": issue_type.name in (cf.required_for or []),
                    "schema": {
                        "type": cf.schema_type or cf.field_type,
                        "custom": cf.schema_custom,
                        "customId": int(cf.field_id.replace("customfield_", ""))
                    },
                    "name": cf.name
                }
                
                # Add allowed values if present
                if cf.allowed_values:
                    field_def["allowedValues"] = [
                        {"value": val} for val in cf.allowed_values
                    ]
                else:
                    field_def["allowedValues"] = []
                
                fields[cf.field_id] = field_def
            
            issuetypes_data.append({
                "self": f"http://localhost:8080/rest/api/2/issuetype/{issue_type.id}",
                "id": str(issue_type.id),
                "name": issue_type.name,
                "fields": fields
            })
        
        projects_data.append({
            "self": f"http://localhost:8080/rest/api/2/project/{project.key}",
            "id": str(project.id),
            "key": project.key,
            "name": project.name,
            "issuetypes": issuetypes_data
        })
    
    return {
        "expand": "projects",
        "projects": projects_data
    }
```

---

## 3. Import/Export System

### 3.1 Import Format Specification

**JSON schema for importing complete JIRA configuration (version 1.0):**

```json
{
  "version": "1.0",
  "metadata": {
    "exported_at": "2026-04-03T10:30:00Z",
    "source": "Manual configuration",
    "description": "Enterprise JIRA configuration"
  },
  "statuses": [
    {
      "status_id": "1",
      "name": "To Do",
      "description": "Work not started",
      "status_category": "new",
      "icon_url": "http://localhost:8080/images/icons/statuses/open.png"
    },
    {
      "status_id": "3",
      "name": "In Progress",
      "status_category": "indeterminate"
    },
    {
      "status_id": "10000",
      "name": "Done",
      "status_category": "done"
    }
  ],
  "custom_fields": [
    {
      "field_id": "customfield_10001",
      "name": "Story Points",
      "field_type": "number",
      "description": "Effort estimation in story points",
      "schema_type": "number",
      "schema_custom": "com.atlassian.jira.plugin.system.customfieldtypes:float",
      "required_for": ["Story", "Epic"],
      "allowed_values": [],
      "available_for": ["Story", "Epic", "Task"]
    },
    {
      "field_id": "customfield_10002",
      "name": "Team",
      "field_type": "option",
      "schema_type": "option",
      "schema_custom": "com.atlassian.jira.plugin.system.customfieldtypes:select",
      "required_for": [],
      "allowed_values": ["Platform", "SaaS", "Cloud", "AI"],
      "available_for": ["Bug", "Story", "Task", "Epic"]
    }
  ],
  "workflows": [
    {
      "workflow_id": "1",
      "name": "Default Workflow",
      "description": "Standard workflow for all issue types",
      "statuses": [
        {"status_id": "1", "sequence": 1},
        {"status_id": "3", "sequence": 2},
        {"status_id": "10000", "sequence": 3}
      ]
    }
  ],
  "project": {
    "key": "PROJ",
    "name": "Project Name",
    "workflows": [
      {
        "issue_type": "Bug",
        "workflow_id": "1"
      },
      {
        "issue_type": "Story",
        "workflow_id": "1"
      }
    ]
  }
}
```

### 3.2 Import Admin API

**POST /api/admin/import/full-config**

Import complete JIRA configuration from JSON.

**Request:**
- Content-Type: `multipart/form-data`
- Body: File upload with JSON data

**Response:**

```json
{
  "success": true,
  "imported": {
    "statuses": 3,
    "custom_fields": 2,
    "workflows": 1,
    "project_workflows": 3
  },
  "errors": []
}
```

**Implementation:**

```python
# src/jira_emulator/routers/admin.py
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import json
from ..database import get_db
from ..models.status import Status
from ..models.custom_field import CustomField
from ..models.workflow import Workflow, WorkflowStatus
from ..models.project import Project
from ..models.issue_type import IssueType
from ..models.project_workflow import ProjectWorkflow

router = APIRouter()

@router.post("/api/admin/import/full-config")
async def import_full_config(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """Import complete JIRA configuration (version 1.0 format)."""
    try:
        content = await file.read()
        config = json.loads(content)
        
        if config.get("version") != "1.0":
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported config version: {config.get('version')}"
            )
        
        imported = {
            "statuses": 0,
            "custom_fields": 0,
            "workflows": 0,
            "project_workflows": 0
        }
        errors = []
        
        # Import statuses
        for status_data in config.get("statuses", []):
            try:
                existing = db.query(Status).filter(
                    Status.status_id == status_data["status_id"]
                ).first()
                
                if existing:
                    existing.name = status_data["name"]
                    existing.description = status_data.get("description")
                    existing.status_category = status_data["status_category"]
                    existing.icon_url = status_data.get("icon_url")
                else:
                    status = Status(
                        status_id=status_data["status_id"],
                        name=status_data["name"],
                        description=status_data.get("description"),
                        status_category=status_data["status_category"],
                        icon_url=status_data.get("icon_url")
                    )
                    db.add(status)
                
                imported["statuses"] += 1
            except Exception as e:
                errors.append(f"Status {status_data.get('name')}: {str(e)}")
        
        # Import custom fields
        for field_data in config.get("custom_fields", []):
            try:
                existing = db.query(CustomField).filter(
                    CustomField.field_id == field_data["field_id"]
                ).first()
                
                if existing:
                    existing.name = field_data["name"]
                    existing.field_type = field_data["field_type"]
                    existing.description = field_data.get("description")
                    existing.schema_type = field_data.get("schema_type")
                    existing.schema_custom = field_data.get("schema_custom")
                    existing.required_for = field_data.get("required_for", [])
                    existing.allowed_values = field_data.get("allowed_values", [])
                    existing.available_for = field_data.get("available_for", [])
                else:
                    field = CustomField(
                        field_id=field_data["field_id"],
                        name=field_data["name"],
                        field_type=field_data["field_type"],
                        description=field_data.get("description"),
                        schema_type=field_data.get("schema_type"),
                        schema_custom=field_data.get("schema_custom"),
                        required_for=field_data.get("required_for", []),
                        allowed_values=field_data.get("allowed_values", []),
                        available_for=field_data.get("available_for", [])
                    )
                    db.add(field)
                
                imported["custom_fields"] += 1
            except Exception as e:
                errors.append(f"Field {field_data.get('name')}: {str(e)}")
        
        db.commit()
        
        # Import workflows
        for workflow_data in config.get("workflows", []):
            try:
                existing = db.query(Workflow).filter(
                    Workflow.workflow_id == workflow_data["workflow_id"]
                ).first()
                
                if existing:
                    workflow = existing
                    workflow.name = workflow_data["name"]
                    workflow.description = workflow_data.get("description")
                    db.query(WorkflowStatus).filter(
                        WorkflowStatus.workflow_id == workflow.id
                    ).delete()
                else:
                    workflow = Workflow(
                        workflow_id=workflow_data["workflow_id"],
                        name=workflow_data["name"],
                        description=workflow_data.get("description")
                    )
                    db.add(workflow)
                    db.flush()
                
                # Add workflow statuses
                for status_data in workflow_data.get("statuses", []):
                    status = db.query(Status).filter(
                        Status.status_id == status_data["status_id"]
                    ).first()
                    
                    if status:
                        ws = WorkflowStatus(
                            workflow_id=workflow.id,
                            status_id=status.id,
                            sequence=status_data["sequence"]
                        )
                        db.add(ws)
                
                imported["workflows"] += 1
            except Exception as e:
                errors.append(f"Workflow {workflow_data.get('name')}: {str(e)}")
        
        db.commit()
        
        # Import project workflows
        project_config = config.get("project", {})
        if project_config:
            project = db.query(Project).filter(
                Project.key == project_config["key"]
            ).first()
            
            if not project:
                project = Project(
                    key=project_config["key"],
                    name=project_config["name"]
                )
                db.add(project)
                db.flush()
            
            for wf_mapping in project_config.get("workflows", []):
                try:
                    issue_type = db.query(IssueType).filter(
                        IssueType.name == wf_mapping["issue_type"]
                    ).first()
                    
                    workflow = db.query(Workflow).filter(
                        Workflow.workflow_id == wf_mapping["workflow_id"]
                    ).first()
                    
                    if issue_type and workflow:
                        existing_mapping = db.query(ProjectWorkflow).filter(
                            ProjectWorkflow.project_id == project.id,
                            ProjectWorkflow.issue_type_id == issue_type.id
                        ).first()
                        
                        if existing_mapping:
                            existing_mapping.workflow_id = workflow.id
                        else:
                            pw = ProjectWorkflow(
                                project_id=project.id,
                                issue_type_id=issue_type.id,
                                workflow_id=workflow.id
                            )
                            db.add(pw)
                        
                        imported["project_workflows"] += 1
                except Exception as e:
                    errors.append(f"Project workflow {wf_mapping}: {str(e)}")
        
        db.commit()
        
        return {
            "success": True,
            "imported": imported,
            "errors": errors
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON format")
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
```

### 3.3 Export Admin API

**GET /api/admin/export/full-config**

Export complete JIRA configuration as JSON.

**Implementation:**

```python
@router.get("/api/admin/export/full-config")
async def export_full_config(db: Session = Depends(get_db)):
    """Export complete JIRA configuration."""
    from datetime import datetime
    
    # Export statuses
    statuses = db.query(Status).all()
    statuses_data = [
        {
            "status_id": s.status_id,
            "name": s.name,
            "description": s.description,
            "status_category": s.status_category,
            "icon_url": s.icon_url
        }
        for s in statuses
    ]
    
    # Export custom fields
    custom_fields = db.query(CustomField).all()
    fields_data = [
        {
            "field_id": cf.field_id,
            "name": cf.name,
            "field_type": cf.field_type,
            "description": cf.description,
            "schema_type": cf.schema_type,
            "schema_custom": cf.schema_custom,
            "required_for": cf.required_for or [],
            "allowed_values": cf.allowed_values or [],
            "available_for": cf.available_for or []
        }
        for cf in custom_fields
    ]
    
    # Export workflows
    workflows = db.query(Workflow).all()
    workflows_data = []
    
    for wf in workflows:
        workflow_statuses = db.query(WorkflowStatus, Status).join(
            Status, WorkflowStatus.status_id == Status.id
        ).filter(
            WorkflowStatus.workflow_id == wf.id
        ).order_by(WorkflowStatus.sequence).all()
        
        workflows_data.append({
            "workflow_id": wf.workflow_id,
            "name": wf.name,
            "description": wf.description,
            "statuses": [
                {
                    "status_id": status.status_id,
                    "sequence": ws.sequence
                }
                for ws, status in workflow_statuses
            ]
        })
    
    # Export project
    project = db.query(Project).first()
    project_data = None
    
    if project:
        project_workflows = db.query(ProjectWorkflow, IssueType, Workflow).join(
            IssueType, ProjectWorkflow.issue_type_id == IssueType.id
        ).join(
            Workflow, ProjectWorkflow.workflow_id == Workflow.id
        ).filter(
            ProjectWorkflow.project_id == project.id
        ).all()
        
        project_data = {
            "key": project.key,
            "name": project.name,
            "workflows": [
                {
                    "issue_type": it.name,
                    "workflow_id": wf.workflow_id
                }
                for pw, it, wf in project_workflows
            ]
        }
    
    return {
        "version": "1.0",
        "metadata": {
            "exported_at": datetime.utcnow().isoformat() + "Z",
            "source": "jira-emulator",
            "description": "JIRA configuration export"
        },
        "statuses": statuses_data,
        "custom_fields": fields_data,
        "workflows": workflows_data,
        "project": project_data
    }
```

---

## 4. Seed Data

**Default seed data with metadata:**

```python
# src/jira_emulator/seed_data.py
DEFAULT_STATUSES = [
    {
        "status_id": "1",
        "name": "To Do",
        "description": "Work not started",
        "status_category": "new",
        "icon_url": "http://localhost:8080/images/icons/statuses/open.png"
    },
    {
        "status_id": "3",
        "name": "In Progress",
        "description": "Work is in progress",
        "status_category": "indeterminate",
        "icon_url": "http://localhost:8080/images/icons/statuses/inprogress.png"
    },
    {
        "status_id": "10000",
        "name": "Done",
        "description": "Work completed",
        "status_category": "done",
        "icon_url": "http://localhost:8080/images/icons/statuses/closed.png"
    }
]

DEFAULT_CUSTOM_FIELDS = [
    {
        "field_id": "customfield_10001",
        "name": "Story Points",
        "field_type": "number",
        "description": "Effort estimation in story points",
        "schema_type": "number",
        "schema_custom": "com.atlassian.jira.plugin.system.customfieldtypes:float",
        "required_for": ["Story", "Epic"],
        "allowed_values": [],
        "available_for": ["Story", "Epic", "Task"]
    },
    {
        "field_id": "customfield_10002",
        "name": "Team",
        "field_type": "option",
        "description": "Team responsible for the work",
        "schema_type": "option",
        "schema_custom": "com.atlassian.jira.plugin.system.customfieldtypes:select",
        "required_for": [],
        "allowed_values": ["Platform", "SaaS", "Cloud", "AI"],
        "available_for": ["Bug", "Story", "Task", "Epic"]
    }
]

DEFAULT_WORKFLOWS = [
    {
        "workflow_id": "1",
        "name": "Default Workflow",
        "description": "Standard three-state workflow",
        "statuses": [
            {"status_id": "1", "sequence": 1},
            {"status_id": "3", "sequence": 2},
            {"status_id": "10000", "sequence": 3}
        ]
    }
]
```

---

## 5. Testing Strategy

### 5.1 Unit Tests

```python
# tests/test_custom_fields.py
def test_get_fields_with_metadata(client, db):
    """Test GET /rest/api/2/field returns metadata."""
    response = client.get("/rest/api/2/field")
    assert response.status_code == 200
    
    fields = response.json()
    story_points = next(f for f in fields if f["id"] == "customfield_10001")
    
    assert story_points["required_for"] == ["Story", "Epic"]
    assert story_points["available_for"] == ["Story", "Epic", "Task"]

def test_get_createmeta_with_validation(client, db):
    """Test field validation in createmeta."""
    response = client.get("/rest/api/2/issue/createmeta?projectKeys=PROJ&issuetypeNames=Bug")
    assert response.status_code == 200
    
    data = response.json()
    bug_fields = data["projects"][0]["issuetypes"][0]["fields"]
    team_field = bug_fields["customfield_10002"]
    
    assert len(team_field["allowedValues"]) == 4

# tests/test_statuses.py
def test_get_all_statuses(client, db):
    """Test GET /rest/api/2/status."""
    response = client.get("/rest/api/2/status")
    assert response.status_code == 200
    
    statuses = response.json()
    todo = next(s for s in statuses if s["name"] == "To Do")
    assert todo["statusCategory"]["key"] == "new"

# tests/test_import_export.py
def test_import_full_config(client, db):
    """Test POST /api/admin/import/full-config."""
    config = {
        "version": "1.0",
        "statuses": [{"status_id": "99", "name": "Custom", "status_category": "new"}],
        "custom_fields": [],
        "workflows": [],
        "project": {}
    }
    
    files = {"file": ("config.json", json.dumps(config), "application/json")}
    response = client.post("/api/admin/import/full-config", files=files)
    
    assert response.status_code == 200
    assert response.json()["success"] == True
```

---

## 6. Documentation

### 6.1 README Update

```markdown
## Enhanced Features

jira-emulator now supports:

### Field Metadata
- **required_for**: Which issue types require the field
- **allowed_values**: Valid dropdown values
- **available_for**: Which issue types can use the field

### Status & Workflow APIs
- `GET /rest/api/2/status` - List all statuses
- `GET /rest/api/2/project/{key}` - Get project with workflows

### Import/Export
- `POST /api/admin/import/full-config` - Import configuration
- `GET /api/admin/export/full-config` - Export configuration

See docs/IMPORT-FORMAT.md for JSON schema.
```

---

## 7. Implementation Roadmap

### Phase 1: Database & Models
- [ ] Update CustomField model with metadata columns
- [ ] Create Status, Workflow, WorkflowStatus, ProjectWorkflow models
- [ ] Update seed data with metadata
- [ ] Test database schema

### Phase 2: Read APIs
- [ ] Implement enhanced GET /rest/api/2/field
- [ ] Implement GET /rest/api/2/status
- [ ] Implement enhanced GET /rest/api/2/project/{key}
- [ ] Implement GET /rest/api/2/issue/createmeta
- [ ] Write unit tests

### Phase 3: Import/Export
- [ ] Implement POST /api/admin/import/full-config
- [ ] Implement GET /api/admin/export/full-config
- [ ] Write integration tests

### Phase 4: Documentation
- [ ] Update README
- [ ] Create API documentation
- [ ] Create import format specification
- [ ] Add code examples

---

## 8. Success Criteria

**Complete When:**
- ✅ All database models created
- ✅ All read APIs implemented
- ✅ Import/export APIs functional
- ✅ Can import configuration and use it
- ✅ All tests passing
- ✅ Documentation complete

---

*This specification defines jira-emulator's own standard for configuration management, independent of any external tools.*
