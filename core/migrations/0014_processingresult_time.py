# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-03-22 09:48
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0013_auto_20170321_1545'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingresult',
            name='time',
            field=models.FloatField(default=0),
        ),
    ]