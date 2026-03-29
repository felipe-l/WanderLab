"""Pipeline run context manager for status tracking."""

import logging
import traceback
from datetime import date, timedelta

from shared.discord_webhook import post_alert, post_log
from shared.supabase_client import create_run, get_latest_run_id, update_run_status

logger = logging.getLogger(__name__)


def current_monday() -> date:
    """Return the Monday of the current week."""
    today = date.today()
    return today - timedelta(days=today.weekday())


class PipelineRunContext:
    """Async context manager that wraps an agent's execution.

    Handles:
    - Creating/fetching the pipeline run for this week
    - Setting status to 'running' on entry
    - Setting status to 'done' on success
    - Setting status to 'failed' on exception
    - Posting status updates to Discord #agent-logs

    Usage:
        async with PipelineRunContext("scout") as ctx:
            run_id = ctx.run_id
            # do work...
            ctx.set_count(42)  # sets scout_raw_count
    """

    def __init__(self, agent_name: str, week_of: date | None = None, run_id: str | None = None):
        self.agent_name = agent_name
        self.week_of = week_of or current_monday()
        self._existing_run_id = run_id  # downstream agents pass this to reuse Scout's run
        self.run_id: str | None = None
        self._count: int | None = None

    async def __aenter__(self):
        if self._existing_run_id:
            self.run_id = self._existing_run_id
        else:
            run = create_run(self.week_of)
            self.run_id = run["id"]
        update_run_status(self.run_id, self.agent_name, "running")
        await post_log(f"Starting pipeline run for week of {self.week_of}")
        logger.info(f"Pipeline run {self.run_id} started for {self.agent_name}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            kwargs = {}
            if self._count is not None:
                count_key = {
                    "scout": "raw_count",
                    "ranker": "cluster_count",
                    "filter": "scored_count",
                    "analyst": "brief_count",
                }.get(self.agent_name)
                if count_key:
                    kwargs[count_key] = self._count
            update_run_status(self.run_id, self.agent_name, "done", **kwargs)
            msg = f"Completed successfully"
            if self._count is not None:
                msg += f" ({self._count} records)"
            await post_log(msg)
            logger.info(f"Pipeline run {self.run_id} completed for {self.agent_name}")
        else:
            error_msg = f"{exc_type.__name__}: {exc_val}"
            update_run_status(self.run_id, self.agent_name, "failed", error=error_msg)
            await post_alert(f"FAILED — {error_msg}")
            logger.error(f"Pipeline run {self.run_id} failed for {self.agent_name}", exc_info=(exc_type, exc_val, exc_tb))
        return False  # Don't suppress exceptions

    def set_count(self, count: int):
        """Set the record count to report on completion."""
        self._count = count
