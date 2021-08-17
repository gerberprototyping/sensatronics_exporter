#!/usr/bin/env python3
from prometheus_client import start_http_server, Info, Gauge
import xml.etree.ElementTree as ETree
import socket, time

SENSATRONICS_HOST = 'sense'
SENSATRONICS_PORT = 80

METRICS_PORT = 9862
REFRESH_PERIOD_SECONDS = 60

PROBE_LABELS = ['probe_id','type','xtype','name','units']


def getRawXML(document):
  REQUEST = "GET %s HTTP/0.9\r\n\r\n\r\n" % document
  client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  client.connect((SENSATRONICS_HOST,SENSATRONICS_PORT))
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


def initMetrics():
  config = ETree.fromstring(getRawXML('/xmlconfig'))
  for child in config:
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
  info_metric = Info('sensatronics_info', 'Sensatronics device info')
  info_metric.info({
    'device_id': config.attrib['id'],
    'name': name,
    'model': model,
    'serial_number': serial_number,
    'fw_release_date': fw_date,
    'fw_version': fw_version,
    'website': website,
  })


def getMetrics(probe_metric):
  data = ETree.fromstring(getRawXML('/xmldata'))
  config = ETree.fromstring(getRawXML('/xmlconfig'))
  probes = {}
  for root in {data, config}:
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
  for probe_id, probe in probes.items():
    labels = []
    for label in PROBE_LABELS:
      if (label in probe):
        labels.append(probe[label])
      else:
        labels.append('')
    probe_metric.labels(*labels).set(probe['value'])





if __name__ == '__main__':
  start_http_server(METRICS_PORT)
  initMetrics()
  probe_metric = Gauge('sensatronics_probe', 'Sensor', labelnames=PROBE_LABELS)
  print('Metrics server started on port %d' % METRICS_PORT)
  while True:
    getMetrics(probe_metric)
    time.sleep(REFRESH_PERIOD_SECONDS)