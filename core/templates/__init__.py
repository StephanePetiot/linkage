from django.middleware.csrf import get_token

from lys import L, raw

from .base import base

TITLEBAR = L.div('.row') / (
    L.div('.col-md-6') / (
        L.a(href='/') / (L.h2 / 'Linkage'),
    ),
    L.div('.col-md-6.text-right') / (
        L.a('.btn.btn-link', href='/admin/logout/', style='margin-top: 20px;display:inline-block') / 'logout',
    )
)

def result(request, graph, result):
    sidebar = ''
    if result:
        sidebar += 'progress: ' + str(int(result.progress*100)) + '\n\n'
        if result.log:
            sidebar += result.log + '\n\n'
        if result.clusters:
            sidebar += 'clusters:\n' + result.clusters + '\n\n'
            sidebar += 'topics:\n' + result.topics + '\n\n'

    return base((
        L.div('.container-fluid') / (
            TITLEBAR,
            L.div('.row') / (
                L.div('.col-md-2') / (
                    L.pre / sidebar
                ),
                L.div('.col-md-10') / (
                    L.ul('.nav.nav-tabs') / (
                        L.li('.active') / (L.a(href='#network', data_toggle='tab') / 'Network'),
                        L.li / (L.a(href='#terms', data_toggle='tab') / 'Terms'),
                        L.li / (L.a(href='#groups', data_toggle='tab') / 'Groups connexions'),
                        L.li / (L.a(href='#topics', data_toggle='tab') / 'Topics connexions'),
                    ),
                    L.div('#outputTabs.tab-content') / (
                        L.div('#network.tab-pane.active') / L.div('#graph'),
                        L.div('#terms.tab-pane') / 'terms',
                        L.div('#groups.tab-pane') / 'groups',
                        L.div('#topics.tab-pane') / 'topics',
                    ),
                ),
            ),
        ),
        L.script(src='/static/js/jquery.js'),
        L.script(src='/static/js/tether.js'),
        L.script(src='/static/js/bootstrap.js'),
        L.script(src='/static/js/vivagraph.js'),
        L.script(src='/static/js/papaparse.js'),
        L.script / raw("var GRAPH_ID = {}".format(graph.pk)),
        L.script(src='/static/js/graph.js'),
    ))

def index(request, graphs):
    return base((
        L.div('.container') / (
            TITLEBAR,
            L.div('.row') / (
                L.div('.col-md-6') / (
                    L.p / (
                        L.h4 / 'Import a graph for processing',
                        L.form('.row', method='POST') / (
                            L.input(type='hidden', name='csrfmiddlewaretoken', value=get_token(request)),
                            L.div('.col-md-9') / L.input('.form-control', type='text', name='q'),
                            L.div('.col-md-3') / (
                                L.button('.btn.btn-primary.btn-large', href='#') / 'arXiv topic'
                            ),
                        ),
                        L.br,
                        L.form('.row', method="post", enctype="multipart/form-data") / (
                            L.input(type='hidden', name='csrfmiddlewaretoken', value=get_token(request)),
                            L.div('.col-md-9') / L.input('form-control', type='file', name='csv_file'),
                            L.div('.col-md-3') / (
                                L.input('.btn.btn-primary.btn-large', href='#', type='submit', value='Import .csv'),
                            ),
                        )
                    ),
                ),
                (
                    L.div('.col-md-6') / (
                        L.h4 / 'Uploaded graphs',
                        L.ul / (
                            L.li / (
                                L.a(href=graph.get_absolute_url()) / str(graph)
                            ) for graph in graphs),
                    ),
                ) if len(graphs) > 0 else None,
            ),
            L.div('.row') / (
                L.div('.col-md-12 text-center') / (
                    L.hr,
                    L.img(src='/static/img/descartes.png', height='60'),
                    raw('&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;'), # dat spacer
                    L.img(src='/static/img/map5.jpg', height='60'),
                ),
            )
        ),
    ))
