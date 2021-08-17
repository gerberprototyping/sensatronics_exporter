#!/usr/bin/env python3
import xml.etree.ElementTree as ETree
import socket, time

from prometheus_client.core import GaugeMetricFamily, InfoMetricFamily
from prometheus_client.utils import floatToGoString
from flask import Flask, request, make_response
from markupsafe import escape


DEFAULT_TARGET_PORT = 80
METRICS_PORT = 9862

PROBE_LABELS = ['probe_id','type','xtype','name','units']


app = Flask(__name__)


    

def getRawXML(host, port, document):
  REQUEST = "GET %s HTTP/0.9\r\n\r\n\r\n" % document
  client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  client.connect((host,port))
  client.send(REQUEST.encode())
  xml = ''
  done = False
  try:
    while(not done):
      response = client.recv(1024)
      if (response == b''):
        done = True
      else:
        xml += response.decode(encoding='UTF-8', errors='ignore')
  finally:
    client.close
  return xml


def getInfo(configXML):
  for child in configXML:
    if (child.tag == 'Unit'):
      for unit_child in child:
        if (unit_child.tag == 'Name'):
          name = unit_child.text
        elif (unit_child.tag == 'Model'):
          model = unit_child.text
        elif (unit_child.tag == 'Serial_Number'):
          serial_number = unit_child.text
        elif (unit_child.tag == 'Firmware_Release_Date'):
          fw_date = unit_child.text
        elif (unit_child.tag == 'Firmware_Version'):
          fw_version = unit_child.text
        elif (unit_child.tag == 'Website'):
          website = unit_child.text
  infoMetric = InfoMetricFamily('sensatronics', 'Sensatronics device info', {
    'device_id': configXML.attrib['id'],
    'name': name,
    'model': model,
    'serial_number': serial_number,
    'fw_release_date': fw_date,
    'fw_version': fw_version,
    'website': website,
  })
  return infoMetric


def getProbes(dataXML, configXML):
  probes = {}
  for root in {dataXML, configXML}:
    for group in root:
      if (group.tag == 'Group'):
        for probe in group:
          if (probe.tag == 'Probe'):
            probe_id = group.attrib['id'] + '.' + probe.attrib['id']
            if (not probe_id in probes):
              probes[probe_id] = {}
            probes[probe_id]['probe_id'] = probe_id
            for k, v in probe.attrib.items():
              if (k != 'id'):
                probes[probe_id][k.lower()] = v
            for probe_child in probe:
              probes[probe_id][probe_child.tag.lower()] = probe_child.text
  probeMetric = GaugeMetricFamily('sensatronics_probe', 'Sensor', labels=PROBE_LABELS)
  for probe_id, probe in probes.items():
    labels = []
    for label in PROBE_LABELS:
      if (label in probe):
        labels.append(probe[label])
      else:
        labels.append('')
    probeMetric.add_metric(labels, probe['value'])
  return probeMetric


def generateMetrics(*metrics):
  """based on prometheus_client.exposition.generate_latest"""

  def sample_line(line):
    if line.labels:
      labelstr = '{{{0}}}'.format(','.join(
        ['{0}="{1}"'.format(
          k, v.replace('\\', r'\\').replace('\n', r'\n').replace('"', r'\"'))
          for k, v in sorted(line.labels.items())]))
    else:
      labelstr = ''
    timestamp = ''
    if line.timestamp is not None:
      # Convert to milliseconds.
      timestamp = ' {0:d}'.format(int(float(line.timestamp) * 1000))
    return '{0}{1} {2}{3}\n'.format(
      line.name, labelstr, floatToGoString(line.value), timestamp)
        
  output = []
  for metric in metrics:
    try:
      mname = metric.name
      mtype = metric.type
      # Munging from OpenMetrics into Prometheus format.
      if mtype == 'counter':
        mname = mname + '_total'
      elif mtype == 'info':
        mname = mname + '_info'
        mtype = 'gauge'
      elif mtype == 'stateset':
        mtype = 'gauge'
      elif mtype == 'gaugehistogram':
        # A gauge histogram is really a gauge,
        # but this captures the structure better.
        mtype = 'histogram'
      elif mtype == 'unknown':
        mtype = 'untyped'

      output.append('# HELP {0} {1}\n'.format(
        mname, metric.documentation.replace('\\', r'\\').replace('\n', r'\n')))
      output.append('# TYPE {0} {1}\n'.format(mname, mtype))

      om_samples = {}
      for s in metric.samples:
        for suffix in ['_created', '_gsum', '_gcount']:
          if s.name == metric.name + suffix:
            # OpenMetrics specific sample, put in a gauge at the end.
              om_samples.setdefault(suffix, []).append(sample_line(s))
              break
        else:
          output.append(sample_line(s))
    except Exception as exception:
      exception.args = (exception.args or ('',)) + (metric,)
      raise

    for suffix, lines in sorted(om_samples.items()):
      output.append('# HELP {0}{1} {2}\n'.format(metric.name, suffix,
                      metric.documentation.replace('\\', r'\\').replace('\n', r'\n')))
      output.append('# TYPE {0}{1} gauge\n'.format(metric.name, suffix))
      output.extend(lines)
  return ''.join(output).encode('utf-8')


@app.route('/')
def webroot():
  target = escape(request.args.get('target',''))
  port = int( escape(request.args.get('port',"%d"%DEFAULT_TARGET_PORT)) )
  if (not target):
    return make_response( '<p>Target required</p>', 404 )
  startTime = time.time()
  try:
    dataXML = ETree.fromstring( getRawXML(target,port,'/xmldata') )
    configXML = ETree.fromstring( getRawXML(target,port,'/xmlconfig') )
    infoMetric = getInfo(configXML)
    probeMetric = getProbes(dataXML, configXML)
    scrapeDuration = time.time() - startTime
    scrapeMetric = GaugeMetricFamily('sensatronics_scrape_duration', 'Time to scrape probes in seconds', value=scrapeDuration)
    output = generateMetrics(infoMetric, probeMetric, scrapeMetric)
    response =  make_response( output, 200 )
    response.mimetype = 'text/plain'
    return response
  except Exception:
    return make_response( '<p>Bad Target</p>', 404 )


@app.route('/metrics')
def metrics():
  return webroot()

@app.route('/health')
def health():
  response = make_response('OK', 200)
  response.mimetype = 'text/plain'
  return response




if __name__ == '__main__':
  app.run(host='0.0.0.0',port=METRICS_PORT)
