"""Read-only access to the versioned skill catalog served by the desktop bridge."""


class Skills:
    def __init__(self, call):
        self._call = call

    def list(self, *, offset=0, limit=50, query=None):
        """One bounded page: ``{skills, total, offset, next_offset, problems, problem_count}``.

        Reading the catalog never evaluates graphs, prepares runs or calls models.
        """
        params = {"offset": offset, "limit": limit}
        if query is not None:
            params["query"] = query
        return self._call("skills.list", params)

    def get(self, skill_id, *, version=None):
        """The resolved skill (latest version unless ``version``); unknown ids/versions raise not_found."""
        params = {"id": skill_id}
        if version is not None:
            params["version"] = version
        return self._call("skills.get", params)["skill"]
