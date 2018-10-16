# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2018-10-15 01:26
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pm', '0004_auto_20181015_0926'),
        ('lims', '0006_auto_20181015_0926'),
        ('teacher', '0013_auto_20181012_1059'),
    ]

    operations = [
        migrations.AlterField(
            model_name='sampleinfoform',
            name='saler',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='销售联系人', to=settings.AUTH_USER_MODEL, verbose_name='销售代表'),
        ),
        migrations.AlterField(
            model_name='sampleinfoform',
            name='transform_contact',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='物流联系人', to=settings.AUTH_USER_MODEL, verbose_name='物流联系人'),
        ),
        migrations.DeleteModel(
            name='Employee',
        ),
    ]
