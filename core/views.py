from io import TextIOWrapper
import hashlib
from smtplib import SMTPRecipientsRefused
from functools import wraps

from django import forms
from django.db import IntegrityError
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login as auth_login
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.conf import settings

from social_django.utils import load_strategy
from raven.contrib.django.raven_compat.models import client
import TwitterAPI

from core import templates, models, third_party_import

MAX_JOBS_PER_USER = None if settings.LINKAGE_ENTERPRISE else 10
MAX_REQUESTS_RESULT = None if settings.LINKAGE_ENTERPRISE else 10000
CLUSTERS_MAX = 50 if settings.LINKAGE_ENTERPRISE else 10


class OrgForm(forms.Form):
    org = forms.CharField(required=True)


def org_required():
    """
    Decorator for views that checks that the user has selected an org type
    Also useful to show the user a short tutorial
    """

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if settings.LINKAGE_ENTERPRISE:
                return view_func(request, *args, **kwargs)

            user = request.user
            profile = None
            try:
                profile = models.UserProfile.objects.get(user=user)
                if profile.org_type:
                    return view_func(request, *args, **kwargs)
            except models.UserProfile.DoesNotExist:
                pass
            form = OrgForm()
            if request.method == 'POST':
                form = OrgForm(data=request.POST)
                if form.is_valid():
                    if profile:
                        profile.org_type = form.cleaned_data['org']
                        profile.save()
                    else:
                        models.UserProfile(user=user, org_type=form.cleaned_data['org']).save()
                    request.method = 'GET'
                    request.POST = {} # hack - should do a redirect
                    return view_func(request, *args, **kwargs)
            return HttpResponse(templates.intro(request, form, ''))
        return _wrapped_view
    return decorator


@login_required
@org_required()
def index(request):
    from config.celery import import_graph_data, retrieve_graph_data

    user_jobs = models.Graph.objects.filter(user=request.user, job_error_log='').order_by('-pk')
    if not request.user.is_staff and MAX_JOBS_PER_USER and user_jobs.count() > MAX_JOBS_PER_USER:
        messages = [('danger', 'You are limited to %d jobs, please delete previous ones before importing a new one' % MAX_JOBS_PER_USER)]
        return HttpResponse(templates.index(
            request,
            messages,
            '__no_import_type__',
            quota_exceeded=True,
        ))

    messages = []
    graph = None
    if request.POST and request.POST['action'] == 'import':
        clusters_min, clusters_max,topics_min, topics_max, \
            limit, valid_parameters = None, None, None, None, 200, True
        filter_largest_subgraph = 'filter_largest_subgraph' in request.POST
        if request.POST['clustering'] == 'manual':
            try:
                clusters_min = int(request.POST['clusters_min'])
                clusters_max = int(request.POST['clusters_max'])
                topics_min = int(request.POST['topics_min'])
                topics_max = int(request.POST['topics_max'])
                if clusters_min <= 0 or topics_min <= 0 \
                        or clusters_max < clusters_min or topics_max < topics_min:
                    messages.append(['danger', 'Invalid cluster range'])
                    valid_parameters = False
                elif clusters_max > CLUSTERS_MAX or topics_max > CLUSTERS_MAX:
                    messages.append(['danger', 'Invalid cluster range: must be inferior of %d' % CLUSTERS_MAX])
                    valid_parameters = False
            except ValueError:
                messages.append(['danger', 'Invalid cluster parameters']) # todo: proper form validation
                valid_parameters = False
        try:
            limit = int(request.POST.get('limit', limit))
            if MAX_REQUESTS_RESULT:
                limit = min(limit, MAX_REQUESTS_RESULT)
        except ValueError:
            messages.append(['danger', 'Invalid limit']) # todo: proper form validation
            valid_parameters = False
        if valid_parameters:

            def make_graph(name, directed=True):
                graph = models.Graph(name=name,
                    user=request.user, directed=directed)
                if clusters_min:
                    graph.job_param_clusters = clusters_min
                    graph.job_param_clusters_max = clusters_max
                    graph.job_param_topics = topics_min
                    graph.job_param_topics_max = topics_max
                graph.save()
                return graph

            def papers_import(name, method, **kwargs):
                graph = make_graph(name, directed=kwargs.get('directed', False))
                kwargs['filter_largest_subgraph'] = filter_largest_subgraph
                retrieve_graph_data.delay(graph.pk, method, **kwargs)
                return redirect('/jobs/')

            if ('choice_csv' in request.POST or 'choice_mbox' in request.POST) and not request.FILES:
                messages.append(['danger', 'You must include a file to import'])

            elif 'choice_csv' in request.POST:
                if 'csv_file' not in request.FILES:
                    messages.append(['danger', 'You must include a file to import'])
                links = TextIOWrapper(request.FILES['csv_file'].file, encoding='utf-8').read()
                graph = make_graph('CSV import of %s' % (request.FILES['csv_file'].name))
                import_graph_data.delay(graph.pk, links, filter_largest_subgraph)
                return redirect('/jobs/')

            elif 'choice_mbox' in request.POST:
                if 'mbox_file' not in request.FILES:
                    messages.append(['danger', 'You must include a file to import'])
                graph = make_graph('MBOX import of %s' % (request.FILES['mbox_file'].name))
                
                mbox = TextIOWrapper(request.FILES['mbox_file'].file, encoding='utf-8')
                # TODO async conversion to csv
                links = third_party_import.mbox_to_csv(mbox, request.POST.get('mbox_subject_only'))
                import_graph_data.delay(graph.pk, links, filter_largest_subgraph)
                return redirect('/jobs/')
            elif 'choice_coauth' in request.POST:
                q = request.POST['q']
                databases = {
                    'arxiv': 'choice_arxiv' in request.POST,
                    'biorxiv': 'choice_biorxiv' in request.POST,
                    'medrxiv': 'choice_medrxiv' in request.POST,
                    'hal': 'choice_hal' in request.POST,
                    'pubmed': 'choice_pubmed' in request.POST,
                    'pubmed_keywords': 'choice_pubmed_keywords' in request.POST,
                }
                databases_titles = []
                for db, enabled in databases.items():
                    if enabled:
                        databases_titles.append({
                            'arxiv': 'arXiv',
                            'biorxiv': 'bioRxiv',
                            'medrxiv': 'medRxiv',
                            'hal': 'HAL',
                            'pubmed': 'PubMed by abstracts' ,
                            'pubmed_keywords': 'PubMed by keywords',
                        }[db])
                if databases_titles:
                    if len(q) > 0:
                        return papers_import(
                            'Co-authorship (%s) import of search term: %s' % (''.join(databases_titles), q),
                            'coauth_to_csv',
                            q=q, limit=limit, databases=databases,
                        )
                    else:
                        messages.append(['danger', 'You must include a search term to do a query'])
                else:
                    messages.append(['danger', 'You must include a database to do a query'])
            elif 'choice_pubmed_citations' in request.POST:
                q = request.POST['q']
                if len(q) > 0:
                    return papers_import(
                        'PubMed citation-network import of search term: %s' % (q, ),
                        'pubmed_citations_to_csv',
                        q=q, limit=limit, directed=True
                    )
                else:
                    messages.append(['danger', 'You must include a search term to do a query'])
            elif 'choice_twitter' in request.POST:
                q = request.POST['q']
                if len(q) > 0:
                    name = 'Twitter import of search term: %s' % (q, )
                    if request.POST.get('use_loklak'):
                        return papers_import(
                            name,
                            'loklak_to_csv',
                            q=q, limit=limit,
                            ignore_self_loop=False,
                        )
                    else:
                        # TODO capture exception inside celery job
                        try:
                            return papers_import(
                                name,
                                'twitter_to_csv',
                                q=q, limit=limit,
                                ignore_self_loop=False,
                                directed=True
                            )
                        except TwitterAPI.TwitterRequestError as e:
                            messages.append(['danger', str(e)])
                            links = ''
                else:
                    messages.append(['danger', 'You must include a search term to do a query'])
            elif 'choice_dropdown' in request.POST:
                filename = request.POST['sample_dropdown']
                assert '/' not in filename
                if '.mbox' in filename:
                    content = open('csv_samples/' + filename).readlines()
                    links = third_party_import.mbox_to_csv(content, subject_only=False)
                    data = models.graph_data_from_links(links)
                    graph = models.Graph(name='MBOX import of %s' % (filename), user=request.user, **data)
                elif '.csv' in filename:
                    content = open('csv_samples/' + filename).read()
                    graph = make_graph('CSV import of %s' % (filename))
                    import_graph_data.delay(graph.pk, content, filter_largest_subgraph)
                    return redirect('/jobs/')
            elif 'choice_prev_job' in request.POST:
                prev_job_pk = int(request.POST['job_dropdown'])
                prev_job = models.Graph.objects.get(pk=prev_job_pk)
                if prev_job.user.pk == request.user.pk:
                    graph = models.Graph(name=prev_job.name,
                        user=request.user, directed=prev_job.directed,
                        labels=prev_job.labels,
                        tdm=prev_job.tdm,
                        edges=prev_job.edges,
                        dictionnary=prev_job.dictionnary)
            elif 'choice_gmail' in request.POST:
                social = request.user.social_auth.get(provider='google-gmail')
                access_token = social.get_access_token(load_strategy())
                graph = make_graph('GMail import')
                retrieve_graph_data.delay(graph.pk, 'gmail_to_csv',
                    access_token=access_token,
                    limit=limit,
                    filter_largest_subgraph=filter_largest_subgraph,
                )
                return redirect('/jobs/')
            if graph:
                if len(graph.labels.strip()) < 2:
                    messages.append(['danger', 'There is no data for this graph'])
                else:
                    if clusters_min:
                        graph.job_param_clusters = clusters_min
                        graph.job_param_clusters_max = clusters_max
                        graph.job_param_topics = topics_min
                        graph.job_param_topics_max = topics_max
                    graph.save()

                    from config.celery import process_graph
                    process_graph.delay(graph.pk, ws_delay=2)
                    return redirect('/jobs/')

    gmail_access_accepted = False
    try:
        request.user.social_auth.get(provider='google-gmail')
        gmail_access_accepted = True
    except:
        pass

    return HttpResponse(templates.index(
        request,
        messages,
        request.GET.get('import_type'),
        user_jobs=user_jobs,
        gmail_access_accepted=gmail_access_accepted,
    ))


def result(request, pk):
    graph = get_object_or_404(models.Graph, pk=pk)
    if not graph.public and (request.user.is_anonymous or request.user.pk != graph.user.pk):
        raise PermissionDenied
    result = None
    try:
        result = models.ProcessingResult.objects \
            .filter(graph=graph) \
            .order_by('-crit').exclude(crit=None) \
            .first()
    except:
        pass

    # export scores for histogram
    scores = models.ProcessingResult.objects \
            .filter(graph=graph) \
            .exclude(crit=None) \
            .order_by('-crit') \
            .values_list('param_clusters', 'param_topics', 'crit')
    if len(scores) < 2:
        scores = None
    else:
        scores = list(scores)

    return HttpResponse(templates.result(request, graph, result, scores=scores))


@login_required
def details(request, pk):
    graph = get_object_or_404(models.Graph, pk=pk)
    if request.user.pk != graph.user.pk:
        raise PermissionDenied
    results = models.ProcessingResult.objects \
            .filter(graph=graph) \
            .order_by('-crit')
    return HttpResponse(templates.details(request, graph, results))


def landing(request):
    if 'confirm_email_token' in request.GET:
        user_pk, token = request.GET['confirm_email_token'].split('p', 1)
        user = User.objects.get(pk=int(user_pk))
        if get_user_token(user) == token and not user.is_active:
            user.is_active = True
            user.save()
            auth_login(request, user, 'django.contrib.auth.backends.ModelBackend')
            messages.success(request, 'Account %s confirmed' % user.email)
        return redirect('/')

    if settings.LINKAGE_ENTERPRISE:
        articles = None
    else:
        from blog.models import Article
        articles = Article.objects.all().order_by('-pk').filter(published=True)

    return HttpResponse(templates.landing(request, articles))


def terms(request):
    return HttpResponse(templates.terms(request))


def credits(request):
    return HttpResponse(templates.credits(request))


@login_required
@org_required()
def jobs(request):
    if request.POST and request.POST['action'] == 'delete':
        graph = get_object_or_404(models.Graph, pk=request.POST['graph_id'])
        graph.delete()

    jobs = models.Graph.objects.filter(user=request.user) \
        .order_by('-created_at')

    demo_jobs = models.Graph.objects.filter(public=True) \
        .order_by('-created_at')

    if request.GET.get('as_json'):
        return JsonResponse(templates.api_jobs(jobs, demo_jobs), safe=False) # TODO: review safe=False

    return HttpResponse(templates.jobs(
        request,
        jobs,
        demo_jobs,
    ))

def addjob(request):
    return index(request)

@login_required
def api_result(request, pk):
    graph = get_object_or_404(models.Graph, pk=pk)
    if request.user.pk != graph.user.pk:
        raise PermissionDenied

    result = None

    try:
        clusters = int(request.GET['clusters'])
        topics = int(request.GET['topics'])
        result = models.ProcessingResult.objects \
            .get(graph=graph,
                param_clusters=clusters,
                param_topics=topics)
    except:
        print('no match for clusters/topics')

    if not result:
        try:
            result = models.ProcessingResult.objects \
                .filter(graph=graph) \
                .order_by('-crit') \
                .exclude(crit=None)
            if 'all' not in request.GET:
                result = result.first()
        except:
            print('no match for graph')
    
    if 'zip' in request.GET:
        return HttpResponse(models.export_to_zip(graph, result),
                content_type='application/zip')

    if 'csv' in request.GET:
        return HttpResponse(graph.original_csv, content_type='text/csv')

    return JsonResponse(templates.api_result(request, graph, result))


def api_cluster(request, pk):
    graph = get_object_or_404(models.Graph, pk=pk)
    if not graph.public and (request.user.is_anonymous or request.user.pk != graph.user.pk):
        raise PermissionDenied

    if 'cluster_to_cluster_cutoff' in request.POST:
        graph.cluster_to_cluster_cutoff = float(request.POST['cluster_to_cluster_cutoff'])
        graph.save()
        return JsonResponse({'message': 'ok [cutoff-updated]'})

    clusters = int(request.POST['clusters'])
    topics = int(request.POST['topics'])
    if clusters <= 0 or topics <= 0:
        return JsonResponse({'message': 'error: invalid parameters'})

    result = None
    try:
        result = models.ProcessingResult.objects.get(graph=graph,
            param_clusters=clusters,
            param_topics=topics)
        if result:
            return JsonResponse({
                'message': 'ok [already-clustered]',
                'result': templates.api_result(request, graph, result)['result'],
            })
    except Exception as e: 
        print(e)

    return JsonResponse({'message': 'nok [dynamic-clustering-disabled]'})

    result = models.ProcessingResult(graph=graph, param_clusters=clusters, param_topics=topics)
    result.save()

    from config.celery import process_graph
    process_graph.delay(graph.pk, result.pk, ws_delay=0)

    return JsonResponse({'message': 'ok [clustering-launched]'})

@login_required
def api_clusters_labels(request, pk):
    graph = get_object_or_404(models.Graph, pk=pk)
    if request.user.pk != graph.user.pk:
        raise PermissionDenied

    clusters = int(request.POST['clusters'])
    topics = int(request.POST['topics'])
    result = models.ProcessingResult.objects \
        .get(graph=graph,
            param_clusters=clusters,
            param_topics=topics)

    result.nodes_meta = request.POST['nodes_meta']

    result.save()

    return JsonResponse({'message': 'ok [nodes-meta-saved]'})


from django.contrib.auth.views import login as login_view
from django.contrib.auth import logout as auth_logout

def login(request):
    message = None
    if request.POST:
        login_view(request)
        if request.user.is_authenticated():

            # logout all other sessions for this user to limit multiples devices using the same user
            if settings.LINKAGE_ENTERPRISE:
                from importlib import import_module
                import datetime

                from django.contrib.sessions.models import Session
                from django.http import HttpRequest

                now = datetime.datetime.now()
                sessions = Session.objects.filter(expire_date__gt=now)

                for session in sessions:
                    username = session.get_decoded().get('_auth_user_id')
                    if str(request.user.id) == username and session.session_key != request.session.session_key:
                        engine = import_module(settings.SESSION_ENGINE)
                        request2 = HttpRequest()
                        request2.session = engine.SessionStore(session.session_key)
                        auth_logout(request2)
                        print('    Successfully logout other device for %r user.' % username)

            return redirect('/jobs/add/')
        else:
            message = "Please enter a correct username and password"
    return HttpResponse(templates.login(request, message, SignupForm()))

class SignupForm(forms.Form):
    email = forms.EmailField(required=True)
    password = forms.CharField(required=True)

# TODO: get rid of homemade protocol and get a real random token
def get_user_token(user):
    return hashlib.sha512(('%s %s %s' % (user.pk, user.email, settings.SECRET_KEY)).encode()).hexdigest()

def signup(request):
    message = None
    form = SignupForm()
    if request.method == 'POST':
        form = SignupForm(data=request.POST)
        if request.POST['simple_captcha'] != request.POST['simple_captcha_answer']:
            message = 'Wrong answer for the captcha, please retry'
            try:
                raise Exception('wrong captcha')
            except:
                client.captureException()
        elif not request.POST.get('accept_terms'):
            message = 'You must accept the terms of services'
        elif form.is_valid():
            email, password = form.cleaned_data['email'], form.cleaned_data['password']
            email_domain = email.split('@')[1]
            # if email_domain not in ('parisdescartes.fr', 'univ-paris1.fr', 'dam.io'):
            #     message = 'Email domain is restricted during the beta period, please contact us if you want an account'
            # else:
            user = None
            try:
                user = User.objects.create_user(email, email, password)
            except IntegrityError as e:
                client.captureException()
                message = 'An user with the same email already exists. If you already tried to sign up, you should check your emails for a confirmation link'
            if user:
                user.is_active = False
                user.save()

                try:
                    raise Exception('User created: {}'.format(email))
                except:
                    client.captureException()

                token = str(user.pk) + 'p' + get_user_token(user)
                try:
                    send_mail('[linkage.fr] Account confirmation', """Welcome to linkage.fr.

You are just one click away from getting an account, click on the following link to confirm your account:
https://linkage.fr/?confirm_email_token=%s
""" % token, 'no-reply@linkage.fr', [email], fail_silently=False)
                    messages.success(request, 'An email has been sent to %s to confirm the account creation' % email)
                    return redirect('/')
                except SMTPRecipientsRefused:
                    message = "Failed to send the confirmation link to your email, please verify it's correct"
                    user.delete()
        else:
            message = 'Invalid email/password'

    return HttpResponse(templates.signup(request, form, message))


def logout(request):
    auth_logout(request)
    return redirect('/')


def handler_generic_error(code, message):
    def handle(request):
        return HttpResponse(templates.error(request, code, message), status=code)
    return handle

handler404 = handler_generic_error(404, 'Page not found')
handler500 = handler_generic_error(500, 'A server error occured and has been reported')
handler403 = handler_generic_error(403, 'Permission Denied')
