from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)


class RightsStatus(StrEnum):
    DECLARED = "declared"
    NOT_DECLARED = "not_declared"


class JobState(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProjectCreate(ApiModel):
    title: str = Field(min_length=1, max_length=200)
    author: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    rights_status: RightsStatus = Field(alias="rightsStatus")

    @model_validator(mode="after")
    def require_rights_declaration(self) -> Self:
        if self.rights_status is not RightsStatus.DECLARED:
            raise ValueError("A declared rights status is required to create a project.")
        return self


class Project(ApiModel):
    id: str
    title: str
    author: str | None = None
    description: str | None = None
    rights_status: RightsStatus = Field(alias="rightsStatus")
    status: str
    artifact_path: str = Field(alias="artifactPath")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")


class Job(ApiModel):
    id: str
    project_id: str | None = Field(default=None, alias="projectId")
    job_type: str = Field(alias="jobType")
    target_id: str | None = Field(default=None, alias="targetId")
    status: JobState
    progress: dict[str, object] = Field(default_factory=dict)
    error_message: str | None = Field(default=None, alias="errorMessage")
    created_at: datetime = Field(alias="createdAt")
    started_at: datetime | None = Field(default=None, alias="startedAt")
    finished_at: datetime | None = Field(default=None, alias="finishedAt")


class RightsDeclaration(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    declaration_type: str = Field(alias="declarationType")
    status: RightsStatus
    created_at: datetime = Field(alias="createdAt")


class Chapter(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    order_index: int = Field(alias="orderIndex")
    status: str


class Scene(ApiModel):
    id: str
    chapter_id: str = Field(alias="chapterId")
    order_index: int = Field(alias="orderIndex")


class Segment(ApiModel):
    id: str
    scene_id: str = Field(alias="sceneId")
    order_index: int = Field(alias="orderIndex")
    text_content: str = Field(alias="textContent")
    status: str


class Character(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    display_name: str = Field(alias="displayName")


class VoiceProfile(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    name: str
    backend: str


class Issue(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    severity: str
    category: str
    title: str


class ExportPackage(ApiModel):
    id: str
    project_id: str = Field(alias="projectId")
    format: str
    status: str
