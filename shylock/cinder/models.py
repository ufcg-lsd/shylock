from django.db import models
from django.db.models.fields.related import ForeignKey
from keystone.models import Projects


class Volumes(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.TextField(default='', null=True)
    availability_zone = models.CharField(max_length=200)
    bootable = models.CharField(max_length=50)
    encrypted = models.BooleanField()
    created_at = models.DateTimeField()
    multiattach = models.BooleanField()
    size = models.IntegerField()
    status = models.CharField(max_length=50)
    updated_at = models.DateTimeField(null=True)
    user_id = models.CharField(max_length=100)
    volume_type = models.CharField(max_length=50, null=True)
    tenant_id = ForeignKey(
        Projects,
        on_delete=models.CASCADE,
        related_name='volumes',
        null=True
    )


class Backups(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=100, null=True)
    description = models.CharField(max_length=255, default='', null=True)
    container = models.CharField(max_length=100)
    availability_zone = models.CharField(max_length=100)
    data_timestamp = models.DateTimeField()
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField(null=True)
    fail_reason = models.CharField(max_length=100, null=True)
    has_dependent_backups = models.BooleanField()
    is_incremental = models.BooleanField()
    object_count = models.IntegerField()
    size = models.IntegerField()
    status = models.CharField(max_length=20)
    volume_id = ForeignKey(
        'Volumes',
        on_delete=models.CASCADE,
        related_name='backup'
    )


class Snapshots(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    size = models.IntegerField()
    status = models.CharField(max_length=20)
    updated_at = models.DateTimeField(null=True)
    volume_id = ForeignKey(
        'Volumes',
        on_delete=models.CASCADE,
        related_name='snapshot_id'
    )
