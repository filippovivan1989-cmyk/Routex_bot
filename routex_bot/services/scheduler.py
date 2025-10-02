"""Scheduler service built around APScheduler."""

from __future__ import annotations

import asyncio
import json
from zoneinfo import ZoneInfo

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from routex_bot.db import Database, Schedule
from routex_bot.services.broadcast import BroadcastService


class SchedulerService:
    """Manage scheduled broadcasts stored in the database."""

    def __init__(
        self,
        db: Database,
        broadcast_service: BroadcastService,
        timezone: str,
    ) -> None:
        self.db = db
        self.broadcast_service = broadcast_service
        self.timezone = ZoneInfo(timezone)
        self.scheduler = AsyncIOScheduler(timezone=self.timezone)
        self.logger = structlog.get_logger(__name__)

    async def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        await self.reload_jobs()

    async def shutdown(self) -> None:
        if self.scheduler.running:
            await self.scheduler.shutdown(wait=False)

    async def reload_jobs(self) -> None:
        for job in self.scheduler.get_jobs():
            job.remove()
        schedules = await self.db.list_schedules()
        for schedule in schedules:
            if schedule.enabled:
                self._add_job(schedule)

    async def add_schedule(
        self,
        name: str,
        schedule_type: str,
        spec: str,
        text: str,
        segment: dict,
    ) -> Schedule:
        schedule_id = await self.db.add_schedule(name, schedule_type, spec, text, segment)
        schedule = await self.db.get_schedule(schedule_id)
        if not schedule:
            raise RuntimeError("Не удалось создать расписание")
        if schedule.enabled:
            self._add_job(schedule)
        return schedule

    def _add_job(self, schedule: Schedule) -> None:
        trigger = self._build_trigger(schedule)
        job_id = f"schedule-{schedule.id}"
        self.scheduler.add_job(
            self._job_runner,
            trigger=trigger,
            id=job_id,
            kwargs={"schedule_id": schedule.id},
            replace_existing=True,
        )
        job = self.scheduler.get_job(job_id)
        if job and job.next_run_time:
            asyncio.create_task(
                self.db.update_schedule_next_run(
                    schedule.id, job.next_run_time.astimezone(ZoneInfo("UTC"))
                )
            )
        self.logger.info("Schedule loaded", schedule_id=schedule.id, next_run=str(job.next_run_time))

    async def toggle_schedule(self, schedule_id: int, enabled: bool) -> None:
        await self.db.set_schedule_enabled(schedule_id, enabled)
        job_id = f"schedule-{schedule_id}"
        if enabled:
            schedule = await self.db.get_schedule(schedule_id)
            if schedule:
                self._add_job(schedule)
        else:
            job = self.scheduler.get_job(job_id)
            if job:
                job.remove()
        await self.db.write_audit(None, "schedule_toggle", {"id": schedule_id, "enabled": enabled})

    async def delete_schedule(self, schedule_id: int) -> None:
        await self.db.delete_schedule(schedule_id)
        job = self.scheduler.get_job(f"schedule-{schedule_id}")
        if job:
            job.remove()
        await self.db.write_audit(None, "schedule_delete", {"id": schedule_id})

    async def _job_runner(self, schedule_id: int) -> None:
        schedule = await self.db.get_schedule(schedule_id)
        if not schedule or not schedule.enabled:
            return
        segment = json.loads(schedule.segment)
        queued, sent, failed = await self.broadcast_service.broadcast(schedule.text, segment, schedule_id=schedule_id)
        self.logger.info(
            "Schedule executed",
            schedule_id=schedule_id,
            queued=queued,
            sent=sent,
            failed=failed,
        )
        job = self.scheduler.get_job(f"schedule-{schedule_id}")
        if job and job.next_run_time:
            await self.db.update_schedule_next_run(
                schedule_id, job.next_run_time.astimezone(ZoneInfo("UTC"))
            )

    def _build_trigger(self, schedule: Schedule) -> CronTrigger | IntervalTrigger:
        if schedule.type == "cron":
            return CronTrigger.from_crontab(schedule.spec, timezone=self.timezone)
        if schedule.type == "interval":
            params = json.loads(schedule.spec)
            return IntervalTrigger(timezone=self.timezone, **params)
        raise ValueError(f"Unsupported schedule type {schedule.type}")

