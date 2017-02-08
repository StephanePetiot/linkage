import csv
from io import TextIOWrapper

from django.shortcuts import render
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from core import templates, models, third_party_import

@login_required
def index(request):
    if request.POST and request.FILES:
        links = TextIOWrapper(request.FILES['csv_file'].file, encoding=request.encoding).read()
        graph = models.Graph(name='CSV import of %s' % (request.FILES['csv_file'].name), links=links)
        graph.save()
        return redirect(graph)
    if request.POST:
        q = request.POST['q']
        links = third_party_import.arxiv_to_csv(q)
        graph = models.Graph(name='arXiv import of search term: %s' % (q, ), links=links)
        graph.save()
        return redirect(graph)
    return HttpResponse(templates.index(request, models.Graph.objects.all().order_by('-imported_at')))


@login_required
def result(request, pk):
    graph = get_object_or_404(models.Graph, pk=pk)
    return HttpResponse(templates.result(request, graph))


@login_required
def api_result(request, pk):
    graph = get_object_or_404(models.Graph, pk=pk)
    return HttpResponse(graph.links)
