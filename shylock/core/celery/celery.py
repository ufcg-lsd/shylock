import os
from datetime import datetime

from core.conf import conf_file
from pytz import timezone

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "conf.settings")

app = Celery("core")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks(['keystone', 'cinder', 'nova', 'monasca', 'core'])

openstack_timer = "*/%d" % conf_file['openstack']['collect_period']
monasca_timer = "*/%d" % conf_file['monasca']['collect_period']

# Aggregate report crontab
crontab_daily_hour = conf_file['billing']['operators']['crontab_daily_hour']
crontab_daily_hour_replaced = timezone(conf_file['billing']['timezone'])\
    .localize(datetime(1970, 1, 1, crontab_daily_hour, 0))\
    .astimezone(timezone('UTC')).hour


app.conf.beat_schedule = {
    # cinder
    "cinder_save_volumes": {
        "task": "cinder.tasks.save_volumes",
        "schedule": crontab(minute=openstack_timer),
    },
    "cinder_save_backups": {
        "task": "cinder.tasks.save_backups",
        "schedule": crontab(minute=openstack_timer),
    },
    "cinder_save_snapshots": {
        "task": "cinder.tasks.save_snapshots",
        "schedule": crontab(minute=openstack_timer),
    },
    # keystone
    "keystone_save_domains": {
        "task": "keystone.tasks.save_domains",
        "schedule": crontab(minute=openstack_timer),
    },
    "keystone_save_projects_and_sponsors": {
        "task": "keystone.tasks.save_projects_and_sponsors",
        "schedule": crontab(minute=openstack_timer),
    },
    "keystone_save_services": {
        "task": "keystone.tasks.save_services",
        "schedule": crontab(minute=openstack_timer),
    },
    "keystone_save_regions": {
        "task": "keystone.tasks.save_regions",
        "schedule": crontab(minute=openstack_timer),
    },
    "keystone_save_quotas": {
        "task": "keystone.tasks.save_quotas",
        "schedule": crontab(minute=openstack_timer),
    },
    # nova
    "nova_save_services": {
        "task": "nova.tasks.save_services",
        "schedule": crontab(minute=openstack_timer),
    },
    "nova_save_hypervisors": {
        "task": "nova.tasks.save_hypervisors",
        "schedule": crontab(minute=openstack_timer),
    },
    "nova_save_aggregates": {
        "task": "nova.tasks.save_aggregates",
        "schedule": crontab(minute=openstack_timer),
    },
    "nova_save_flavors": {
        "task": "nova.tasks.save_flavors",
        "schedule": crontab(minute=openstack_timer),
    },
    "nova_save_servers": {
        "task": "nova.tasks.save_servers",
        "schedule": crontab(minute=openstack_timer),
    },
    "nova_save_instance_actions": {
        "task": "nova.tasks.save_instance_actions",
        "schedule": crontab(minute=openstack_timer),
    },
    # monasca
    "monasca_schedule_save_statistics": {
        "task": "monasca.tasks.schedule_save_statistics",
        "schedule": crontab(minute=monasca_timer),
    },
    # core reports
    "generate_aggregates_report": {
        "task": "core.tasks.generate_aggregates_report",
        "schedule": crontab(
            minute=18,
            hour=crontab_daily_hour_replaced),
        "args": [conf_file['billing']['operators']['send_email'], ],
    },
    "generate_sponsors_report": {
        "task": "core.tasks.generate_sponsors_report",
        "schedule": crontab(
            minute=0,
            hour=0,
            day_of_month=conf_file['billing']['sponsors']['crontab_month_day']),
        "args": [conf_file['billing']['sponsors']['send_email'], ],
    }
}
