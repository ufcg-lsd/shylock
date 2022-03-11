from celery import shared_task
from cinderclient import client as cinder_client
from django.conf import settings

from cinder.models import *

cinder = cinder_client.Client(
    version='3.40',
    session=settings.OPENSTACK_SESSION,
)


@shared_task
def save_volumes() -> None:
    """Create or update existing volumes."""

    # retrieve all services
    volumes = cinder.volumes.list(search_opts={'all_tenants': 1})
    for volume in volumes:
        volume = volume.to_dict()

        try:
            volume_obj = Volumes.objects.get(id=volume['id'])
        except Volumes.DoesNotExist:
            volume_obj = Volumes()

        volume_obj.id = volume['id']
        volume_obj.name = volume['name']
        volume_obj.description = volume['description']
        volume_obj.availability_zone = volume['availability_zone']
        volume_obj.bootable = volume['bootable']
        volume_obj.encrypted = volume['encrypted']
        volume_obj.created_at = volume['created_at'] + 'Z'
        volume_obj.multiattach = volume['multiattach']
        volume_obj.size = volume['size']
        volume_obj.status = volume['status']
        # if date is not empty, add Z at the end to inform UTC timezone
        updated_at = volume.get('updated_at')
        if updated_at:
            updated_at = updated_at + 'Z'
        volume_obj.updated_at = updated_at
        volume_obj.user_id = volume['user_id']
        volume_obj.volume_type = volume['volume_type']
        try:
            project_obj = Projects.objects.get(
                id=volume['os-vol-tenant-attr:tenant_id'])
        except Projects.DoesNotExist:
            project_obj = None
        volume_obj.tenant_id = project_obj
        volume_obj.save()


@shared_task
def save_backups() -> None:
    """Create or update existing backups."""

    # retrieve all services
    backups = cinder.backups.list(search_opts={'all_tenants': 1})
    for backup in backups:
        backup = backup.to_dict()
        try:
            backup_obj = Backups.objects.get(id=backup['id'])
        except Backups.DoesNotExist:
            backup_obj = Backups()

        backup_obj.id = backup['id']
        backup_obj.name = backup['name']
        backup_obj.description = backup['description']
        backup_obj.container = backup['container']
        backup_obj.availability_zone = backup['availability_zone']
        backup_obj.data_timestamp = backup['data_timestamp'] + 'Z'
        backup_obj.created_at = backup['created_at'] + 'Z'
        # if date is not empty, add Z at the end to inform UTC timezone
        updated_at = backup.get('updated_at')
        if updated_at:
            updated_at = updated_at + 'Z'
        backup_obj.updated_at = backup['updated_at']
        backup_obj.fail_reason = backup['fail_reason']
        backup_obj.has_dependent_backups = backup['has_dependent_backups']
        backup_obj.is_incremental = backup['is_incremental']
        backup_obj.object_count = backup['object_count']
        backup_obj.size = backup['size']
        backup_obj.status = backup['status']
        # get volume model
        volume_obj = Volumes.objects.get(id=backup['volume_id'])
        backup_obj.volume_id = volume_obj
        backup_obj.save()


@shared_task
def save_snapshots() -> None:
    """Create or update existing snapshots."""

    # retrieve all snapshots
    snapshots = cinder.volume_snapshots.list(search_opts={'all_tenants': 1})
    for snapshot in snapshots:
        snapshot = snapshot.to_dict()

        try:
            snapshot_obj = Snapshots.objects.get(id=snapshot['id'])
        except Snapshots.DoesNotExist:
            snapshot_obj = Snapshots()

        snapshot_obj.id = snapshot['id']
        snapshot_obj.name = snapshot['name']
        snapshot_obj.description = snapshot['description']
        snapshot_obj.size = snapshot['size']
        snapshot_obj.status = snapshot['status']
        # if date is not empty, add Z at the end to inform UTC timezone
        updated_at = snapshot.get('updated_at')
        if updated_at:
            updated_at = updated_at + 'Z'

        # get volume object
        volume_obj = Volumes.objects.get(id=snapshot['volume_id'])
        snapshot_obj.volume_id = volume_obj

        snapshot_obj.save()
