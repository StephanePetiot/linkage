from io import TextIOWrapper

from django.shortcuts import render
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required

from core import templates, models, third_party_import

@login_required
def index(request):
    graph = None
    if request.POST and request.POST['action'] == 'import':
        clusters, topics = None, None
        if request.POST['clustering'] == 'manual':
            clusters = int(request.POST['clusters'])
            topics = int(request.POST['topics'])
        if request.FILES:
            if 'choice_csv' in request.POST:
                links = TextIOWrapper(request.FILES['csv_file'].file, encoding=request.encoding).read()
                graph = models.Graph(name='CSV import of %s' % (request.FILES['csv_file'].name), links=links, user=request.user)
                graph.save()
            elif 'choice_mbox' in request.POST:
                mbox = TextIOWrapper(request.FILES['csv_file'].file, encoding=request.encoding)
                links = third_party_import.mbox_to_csv(mbox)
                graph = models.Graph(name='MBOX import of %s' % (request.FILES['csv_file'].name), links=links, user=request.user)
                graph.save()
        if 'choice_arxiv' in request.POST:
            q = request.POST['q']
            if len(q) > 0:
                links = third_party_import.arxiv_to_csv(q)
                graph = models.Graph(name='arXiv import of search term: %s' % (q, ), links=links, user=request.user)
                graph.save()
        if graph:
            from config.celery import process_graph
            process_graph.delay(graph.pk, clusters, topics)
            return redirect(graph)

    if request.POST and request.POST['action'] == 'delete':
        graph = get_object_or_404(models.Graph, pk=request.POST['graph_id'])
        graph.delete()
        return redirect('/')

    return HttpResponse(templates.index(request, models.Graph.objects.filter(user=request.user).order_by('-created_at')))

@login_required
def result(request, pk):
    graph = get_object_or_404(models.Graph, pk=pk)
    result = None
    try:
        result = models.ProcessingResult.objects.get(graph=graph)
    except:
        pass
    return HttpResponse(templates.result(request, graph, result))

from django.contrib.auth.views import login as login_view

def login(request):
    message = None
    if request.POST:
        login_view(request)
        if request.user.is_authenticated():
            return redirect('/')
        else:
            message = "Please enter a correct username and password"
    return HttpResponse(templates.login(request, message))

from django.contrib.auth import logout as auth_logout

def logout(request):
    auth_logout(request)
    return redirect('/')
