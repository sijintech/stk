"""Project operations behind the peer authority's current authenticated lease.

Remote callers select an owner-authorized project UUID, grant and database
generation. Local paths, handles and operation scopes never enter this API.
The authority owns authentication, grants, revocation and restore boundaries;
the shared project store owns paging, revision CAS and atomic edit receipts.
"""
from contextlib import contextmanager
from typing import ContextManager, Literal, Protocol
from uuid import UUID

from suan.project import ProjectError, ProjectStore


class _ProjectLease(Protocol):
    store: ProjectStore
    project_id: str
    operation_scope: str


class _ProjectAuthority(Protocol):
    def project_access(self, context: object, project_id: str, *, grant_id: str,
                       database_generation: str,
                       capability: Literal["project.read", "project.edit"]) -> ContextManager[_ProjectLease]: ...


def _project_id(value):
    try:
        if type(value) is not str or len(value) != 36 or str(UUID(value)) != value:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ProjectError("Peer project ID must be a canonical UUID") from None
    return value


class PeerProjects:
    """Restricted project service; each call rechecks the exact grant and generation.

    ``context`` comes from the authority's authentication exchange. The authority
    holds its lease until the entire store call finishes, serializing it against
    grant revocation and database replacement. Its operation scope binds stable
    owner/caller/database-generation identities, including across reconnects.
    """

    def __init__(self, authority: _ProjectAuthority):
        self.authority = authority

    @contextmanager
    def _access(self, context, project_id, grant_id, database_generation, capability):
        project_id = _project_id(project_id)
        with self.authority.project_access(context, project_id, grant_id=grant_id,
                database_generation=database_generation, capability=capability) as lease:
            if lease.project_id != project_id or lease.store.info()["id"] != project_id:
                raise ProjectError("Authorized project identity does not match its database")
            yield lease

    def catalog(self, context, project_id, *, grant_id, database_generation,
                expected_revision=None, offset=0, limit=200):
        """Read bounded structure; continuation pages retain the returned revision."""
        with self._access(context, project_id, grant_id, database_generation, "project.read") as lease:
            return lease.store.catalog(expected_revision=expected_revision, offset=offset, limit=limit)

    def read_table(self, context, project_id, table_id, *, grant_id, database_generation,
                   expected_revision, offset=0, limit=200, record_id=None):
        """Read one bounded record page at an explicit project revision."""
        with self._access(context, project_id, grant_id, database_generation, "project.read") as lease:
            return lease.store.read_table(table_id, expected_revision=expected_revision, offset=offset,
                                          limit=limit, record_id=record_id)

    def apply_once(self, context, project_id, commands, *, grant_id, database_generation,
                   operation_id, expected_revision):
        """Commit one explicit original request, or return its authorized old success."""
        with self._access(context, project_id, grant_id, database_generation, "project.edit") as lease:
            return lease.store.edit_operations.apply_once(commands, operation_id=operation_id,
                expected_revision=expected_revision, scope=lease.operation_scope)

    def get(self, context, project_id, operation_id, *, grant_id, database_generation):
        """Read only this caller's original receipt under its current project grant."""
        with self._access(context, project_id, grant_id, database_generation, "project.read") as lease:
            return lease.store.edit_operations.get(operation_id, scope=lease.operation_scope)


__all__ = ["PeerProjects"]
