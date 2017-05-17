import './graph/csrf.js';

import React from 'react';
import ReactDOM from 'react-dom';

const Icon = props => <span className={'glyphicon glyphicon-' + props.name}></span>;

class Job extends React.Component {
    constructor(props) {
      super(props);
      this.state = {
        deleted: false,
        showLog: false,
      };
      this.toggleShowLog = this.toggleShowLog.bind(this);
      this.doDelete = this.doDelete.bind(this);
    }
    toggleShowLog() {
        this.setState({showLog: !this.state.showLog});
    }
    doDelete() {
      $(this.refs.job).fadeOut( 400, () => this.setState({deleted: true}));
      $.post('/jobs/', {
        'action': 'delete',
        'graph_id': this.props.job.id,
      });
    }
    render() {
      if (this.state.deleted) {
        return <div></div>;
      }
      var job = this.props.job;
      var finished = job.progress == 1 || job.job_error_log !== '';

      if (job.public) {
        return <div>
          {this.props.first_public ? <hr/> : null}
          {this.props.first_public ? <h4>Public jobs you can explore</h4> : null}
          <div className='panel panel-default' ref='job'>
            <div className='panel-heading'><a href={job.url} style={{color: 'inherit'}}>{job.name}</a></div>
          </div>
        </div>
      }

      return <div className='panel panel-default' ref='job'>
        <div className='panel-heading'>{job.name}</div>
        <div className='panel-body'>
          <div className='row'>
            <div className='col-md-5'>
              <div>
                {job.job_param_topics != job.job_param_topics_max || job.job_param_clusters != job.job_param_clusters_max ?
                  <em>
                    Auto-clustering between {job.job_param_topics} to {job.job_param_topics_max} topics
                    {' '}and {job.job_param_clusters} to {job.job_param_clusters_max} clusters
                  </em> :
                  <em>Clustering with {job.job_param_topics} topics and {job.job_param_clusters} clusters</em>
                }
              </div>
              <div>Created: {job.created_at}</div>
              {finished && job.time_t > 0 ?
                <div>Took <strong>{job.time}</strong></div> :
                null // <div>Est. time to process: <strong>3h30</strong> (~<strong>1h05</strong> left)</div>
              }
            </div>
            <div className='col-md-7 text-right'>
              {finished && job.job_error_log === '' ? <span>
                <a className='btn btn-success' href={job.url}>
                  <Icon name='fullscreen'/>&nbsp;&nbsp;View
                </a>
                &nbsp;&nbsp;&nbsp;&nbsp;
                {/*
                <a className='btn btn-warning' href={job.url+'details/'}>Details</a>
                &nbsp;&nbsp;&nbsp;&nbsp;
                */}
                <a className='btn btn-warning' href={job.url + 'data/?all&zip'} download={'job_' + job.id + '_export.zip'}>
                  <Icon name='download'/>&nbsp;&nbsp;Download
                </a>
                &nbsp;&nbsp;&nbsp;&nbsp;
              </span> : null}
              <button className='btn btn-danger' onClick={() => this.doDelete()}>
                <Icon name='trash'/>
              </button>
            </div>
          </div>
          <div className='row'>
            <div className="col-md-12">
                {finished ? null : <div>
                  <br/>
                  <div className="progress progress-striped active">
                      <div className="progress-bar" style={{width: (job.progress * 100).toFixed(2) + '%'}}></div>
                  </div>
                </div>}
                {job.job_error_log !== '' ? <div>
                  <br/>
                  <div className="alert alert-danger">
                    {job.job_error_log}
                  </div>
                </div> : null}
                {/*<div>Log:</div>
                <pre style={{maxHeight: 100}}>{job.log}</pre>*/}
                {/*<pre style={{maxHeight: 100}}>{JSON.stringify(job, null, 2)}</pre>*/}
            </div>
          </div>
        </div>
      </div>;
    }
};


function render() {
  if (JOBS.length == 0) return;
  var first_public_job_found = -1;
  var jobs = JOBS.map((job, i) => {
    if (job.public && first_public_job_found === -1) {
      first_public_job_found = i;
    }
    return <Job job={job} key={i} first_public={i === first_public_job_found} />;
  });
  ReactDOM.render(<div>{jobs}</div>, document.getElementById('_jobs'));
};


var ws_scheme = window.location.protocol == "https:" ? "wss" : "ws";
var socket = new WebSocket(ws_scheme + "://" + window.location.host + '/jobs/');

socket.onmessage = function(e) {
  console.log(e);
  $.getJSON('/jobs/', {
    as_json: true,
  }, function(data) {
    JOBS = data;
    render();
  });
}

// Call onopen directly if socket is already open
if (socket.readyState == WebSocket.OPEN) socket.onopen();

render();
