# -*- coding: utf-8 -*-
# Generated by Django 1.10.4 on 2018-10-15 01:26
from __future__ import unicode_literals

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('pm', '0003_auto_20181012_1436'),
    ]

    operations = [
        migrations.AlterField(
            model_name='subproject',
            name='saleman',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='销售代表', to=settings.AUTH_USER_MODEL, verbose_name='销售代表'),
        ),
        migrations.AlterField(
            model_name='subproject',
            name='sample_customer',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='样品联系人姓名', to=settings.AUTH_USER_MODEL, verbose_name='销售代表'),
        ),
    ]
