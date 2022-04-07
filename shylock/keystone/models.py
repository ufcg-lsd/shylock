from django.db import models
from django.db.models.fields.related import ForeignKey


class Domains(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    description = models.TextField()
    enabled = models.BooleanField()
    name = models.CharField(max_length=200)


class Projects(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    description = models.TextField()
    domain_id = ForeignKey(
        'Domains',
        on_delete=models.CASCADE,
        related_name='projects'
    )
    sponsor = ForeignKey(
        'Sponsors',
        on_delete=models.CASCADE,
        related_name='projects',
        null=True
    )
    enabled = models.BooleanField()
    is_domain = models.BooleanField(default=False)
    name = models.CharField(max_length=200)
    parent_id = models.CharField(max_length=50)


class ProjectQuotas(models.Model):
    project = ForeignKey(
        'Projects',
        on_delete=models.CASCADE,
        related_name='quotas'
    )
    cores = models.IntegerField()
    ram = models.IntegerField()
    instances = models.IntegerField()
    volumes = models.IntegerField()
    gigabytes = models.IntegerField()
    backups = models.IntegerField()
    backup_gigabytes = models.IntegerField()
    snapshots = models.IntegerField()
    floatingip_limit = models.IntegerField()
    floatingip_reserved = models.IntegerField()
    floatingip_used = models.IntegerField()
    loadbalancer_limit = models.IntegerField()
    loadbalancer_reserved = models.IntegerField()
    loadbalancer_used = models.IntegerField()


class Sponsors(models.Model):
    email = models.EmailField()


class Users(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    name = models.CharField(max_length=200)
    default_project_id = ForeignKey(
        'Projects',
        on_delete=models.CASCADE,
        related_name='users'
    )
    domain_id = ForeignKey(
        'Domains',
        on_delete=models.CASCADE,
        related_name='users'
    )
    enabled = models.BooleanField()
    password_expires_at = models.DateTimeField(blank=True, null=True)


class Services(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    description = models.TextField()
    enabled = models.BooleanField()
    name = models.CharField(max_length=50)
    type = models.CharField(max_length=50)


class Regions(models.Model):
    id = models.CharField(primary_key=True, max_length=50)
    description = models.TextField()
    parent_region_id = models.CharField(max_length=50, blank=True, null=True)
