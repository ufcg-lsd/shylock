from django.db import models
from django.db.models.fields.related import (ForeignKey, ManyToManyField,
                                             OneToOneField)
from keystone.models import Projects


class Services(models.Model):
    id = models.IntegerField(primary_key=True)
    binary = models.CharField(max_length=100)
    disabled_reason = models.TextField(blank=True, null=True)
    host = models.CharField(max_length=200)
    state = models.CharField(max_length=10)
    status = models.CharField(max_length=15)
    updated_at = models.DateTimeField(blank=True, null=True)
    zone = models.CharField(max_length=15)


class Hypervisors(models.Model):
    id = models.IntegerField(primary_key=True)
    vendor = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    arch = models.CharField(max_length=100)
    cores = models.IntegerField()
    cells = models.IntegerField()
    threads = models.IntegerField()
    sockets = models.IntegerField()
    host_ip = models.CharField(max_length=100)
    hypervisor_hostname = models.CharField(max_length=100)
    hypervisor_type = models.CharField(max_length=100)
    hypervisor_version = models.CharField(max_length=100)
    local_gb = models.IntegerField()
    local_gb_used = models.IntegerField()
    memory_mb = models.IntegerField()
    memory_mb_used = models.IntegerField()
    running_vms = models.IntegerField()
    service = OneToOneField(
        'Services',
        on_delete=models.CASCADE,
        related_name='hypervisor',
        null=True
    )
    state = models.CharField(max_length=10)
    status = models.CharField(max_length=10)
    vcpus = models.IntegerField()
    vcpus_used = models.IntegerField()


class Aggregates(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100)
    availability_zone = models.CharField(max_length=100)
    created_at = models.DateTimeField()
    deleted_at = models.DateTimeField(blank=True, null=True)
    updated_at = models.DateTimeField(blank=True, null=True)
    deleted = models.BooleanField()
    hosts = ManyToManyField(
        'Services',
        related_name='aggregates',
    )


class Flavors(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=100)
    swap = models.CharField(max_length=100, default='')
    rxtx_factor = models.FloatField()
    is_public = models.BooleanField()
    vcpus = models.IntegerField()
    ram = models.IntegerField()
    disk = models.IntegerField()
    aggregate = ForeignKey(
        'Aggregates',
        on_delete=models.CASCADE,
        related_name='flavors',
        null=True
    )


class Servers(models.Model):
    id = models.UUIDField(primary_key=True)
    name = models.CharField(max_length=100)
    status = models.CharField(max_length=20)
    tenant_id = ForeignKey(
        Projects,
        on_delete=models.CASCADE,
        related_name='servers',
        null=True
    )
    user_id = models.CharField(max_length=100)
    image_id = models.UUIDField(null=True)
    created = models.DateTimeField()
    updated = models.DateTimeField(null=True)
    flavor = ForeignKey(
        'Flavors',
        on_delete=models.CASCADE,
        related_name='servers',
        null=True
    )


class InstanceActions(models.Model):
    """Log of changing states from a server."""
    action = models.CharField(max_length=20)
    instance = ForeignKey(
        'Servers',
        on_delete=models.CASCADE,
        related_name='actions'
    )
    project = ForeignKey(
        Projects,
        on_delete=models.CASCADE,
        related_name='servers_actions',
        null=True
    )
    message = models.CharField(max_length=255, null=True)
    request_id = models.CharField(max_length=80)
    start_time = models.DateTimeField()
    user_id = models.CharField(max_length=80, null=True)


class ServerAddresses(models.Model):
    type = models.CharField(max_length=20)
    addr = models.CharField(max_length=50)
    version = models.IntegerField()
    server = ForeignKey(
        'Servers',
        on_delete=models.CASCADE,
        related_name='addresses'
    )
