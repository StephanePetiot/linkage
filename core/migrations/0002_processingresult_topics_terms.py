# -*- coding: utf-8 -*-
# Generated by Django 1.10 on 2017-02-16 14:57
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='processingresult',
            name='topics_terms',
            field=models.TextField(blank=True, default=''),
        ),
    ]
