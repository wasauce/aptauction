#!/usr/bin/python2.5
#
"""
Django template filters for CallTrends.
"""

__author__ = 'wferrell@ (Bill Ferrell)'
import time
import urllib

from google.appengine.api import datastore
from google.appengine.api import datastore_errors
from google.appengine.api import users
from google.appengine.ext.webapp import template

def hide_referer(url):
  """Modifies the given URL to redirect through Google to hide referers."""
  return 'http://www.google.com/url?sa=D&q=' + urllib.quote(url)

def item(array, index):
  """Returns the item with the given index in the given array."""
  return array[index]


def islist(value):
  """Returns true if the given value is a list.

  Useful when you store lists in the Prometheus datastore since lists of
  length 1 are incorrectly returned as strings.
  """
  return isinstance(value, list)


# Register the filter functions with Django
register = template.create_template_register()
register.filter(hide_referer)
register.filter(item)
register.filter(islist)
