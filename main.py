#!/usr/bin/env python
"""
aptauction

We use the webapp.py WSGI framework to handle CGI requests, using the
wsgiref module to wrap the webapp.py WSGI application in a CGI-compatible
container. See webapp.py for documentation on RequestHandlers and the URL
mapping at the bottom of this module.

We use Django templates, which are described at
http://www.djangoproject.com/documentation/templates/. We define a custom
Django template filter library in templatefilters.py for use in dilbertindex
templates.
"""

__author__ = '(Bill Ferrell)'

import cgi
import datetime
import htmlentitydefs
import math
import os
import re
import sgmllib
import sys
import time
import urllib
import logging
import wsgiref.handlers
import traceback
import random

from google.appengine.api import datastore
from google.appengine.api import datastore_types
from google.appengine.api import datastore_errors
from google.appengine.api import users
from google.appengine.api import memcache
from google.appengine.api import mail
from google.appengine.ext import webapp
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import login_required
from google.appengine.ext import search
from google.appengine.ext import bulkload
from google.appengine.ext import db

## Set logging level.
logging.getLogger().setLevel(logging.INFO)

# Add our custom Django template filters to the built in filters
template.register_template_library('templatefilters')

# Set to true to see stack traces and template debugging information
_DEBUG = True


class ListingModel(db.Model):
  """This is the AppEngine data model for the listings."""

  link = db.LinkProperty()
  openingBid = db.IntegerProperty()
  currentBid = db.IntegerProperty()
  maxBid = db.IntegerProperty()
  listingTitle = db.StringProperty()
  listingAddress = db.StringProperty()
  listingDescription = db.TextProperty()
  endDate = db.DateProperty()
  listingOwner = db.UserProperty()
  listingNickname = db.StringProperty()
  numberOfBids = db.IntegerProperty()
  currentWinningBidderNickname = db.StringProperty()
  creationDate = db.DateTimeProperty(auto_now_add=True)
  listingOpen = bool


class BidHistoryModel(db.Model):
  """This is the AppEngine bid model for the bids."""

  listing = db.ReferenceProperty(ListingModel)
  bid = db.IntegerProperty()
  bidDate = db.DateTimeProperty(auto_now_add=True)
  bidder = db.UserProperty()


class BaseRequestHandler(webapp.RequestHandler):
  """The common class for all aptauction requests"""

  def handle_exception(self, exception, debug_mode):
    exception_name = sys.exc_info()[0].__name__
    exception_details = str(sys.exc_info()[1])
    exception_traceback = ''.join(traceback.format_exception(*sys.exc_info()))
    logging.error(exception_traceback)
    exception_expiration = 600 # seconds 
    mail_admin = "wferrell@gmail.com" # must be an admin -- be sure to remove before committing
    sitename = "aptauction"
    throttle_name = 'exception-'+exception_name
    throttle = memcache.get(throttle_name)
    if throttle is None:
        memcache.add(throttle_name, 1, exception_expiration)
        subject = '[%s] exception [%s: %s]' % (sitename, exception_name,
                                               exception_details)
        mail.send_mail_to_admins(sender=mail_admin,
                                 subject=subject,
                                 body=exception_traceback)

    values = {}
    template_name = 'error.html'
    #if users.is_current_user_admin():
    #    values['traceback'] = exception_traceback
    values['traceback'] = exception_traceback
    directory = os.path.dirname(os.environ['PATH_TRANSLATED'])
    path = os.path.join(directory, os.path.join('templates', template_name))
    self.response.out.write(template.render(path, values, debug=_DEBUG))

  def generate(self, template_name, template_values={}):
    """Generates the given template values into the given template.

    Args:
        template_name: the name of the template file (e.g., 'index.html')
        template_values: a dictionary of values to expand into the template
    """

    # Populate the values common to all templates
    values = {
      #'user': users.GetCurrentUser(),
      'debug': self.request.get('deb'),
      'user': users.GetCurrentUser(),
      'login_url': users.CreateLoginURL(self.request.uri),
      'logout_url': users.CreateLogoutURL(self.request.uri),

    }
    values.update(template_values)
    directory = os.path.dirname(os.environ['PATH_TRANSLATED'])
    path = os.path.join(directory, os.path.join('templates', template_name))
    self.response.out.write(template.render(path, values, debug=_DEBUG))


class HomePageHandler(BaseRequestHandler):
  """  Generates the start/home page.
  """

  def get(self, garbageinput=None):
    logging.info('Visiting the homepage')

    self.generate('home.html', {
    })

class ShowAllListingsPageHandler(BaseRequestHandler):
  """  Generates the Show All Listings Page.
  """

  def get(self):
    logging.info('Visiting the ShowAllListingsPage')

    query = ListingModel.all()

    self.generate('listings.html', {
      'listings': query,
    })

class MyAccountPageHandler(BaseRequestHandler):
  """  Generates the user admin page for them to see or create listings."""

  def get(self):
    logging.info('Visiting the UserAdminPageHandler')
    user = users.get_current_user()

    if user:
        query = ListingModel.all()
        query.filter('listingOwner =', user)

        self.generate('myaccount.html', {
          'listings': query,
        })
    else:
      self.redirect(users.create_login_url(self.request.uri))


class ProcessCreateListingHandler(BaseRequestHandler):
  """  Processes the input of listing page."""

  def get(self):
    logging.info('Visiting the ProcessCreateListingHandler via get. Bad.')
    self.redirect("/createlisting")

  def post(self):
    """ Post method to accept ListingModel data."""
    logging.info('Visiting the ProcessCreateListingHandler via post. Good.')
    user = users.get_current_user()

    if user:
      day = cgi.escape(self.request.get('day'))
      month = cgi.escape(self.request.get('month'))
      year = cgi.escape(self.request.get('year'))
      newlisting = ListingModel()
      newlisting.link = db.Link(cgi.escape(self.request.get('externallistingurl')))
      newlisting.openingBid = int(cgi.escape(self.request.get('openingbid')))
      newlisting.listingAddress = cgi.escape(self.request.get('streetaddress'))
      newlisting.listingTitle = cgi.escape(self.request.get('listingtitle'))
      newlisting.listingDescription = cgi.escape(self.request.get('descriptionofproperty'))
      newlisting.listingOwner = user
      newlisting.listingNickname = user.nickname()
      newlisting.listingOpen = True
      newlisting.numberOfBids = 0
      newlisting.currentBid = 0
      newlisting.maxBid = int(cgi.escape(self.request.get('openingbid')))
   #   newlisting.endDate = datetime.date(year,month,day)
      newlisting.put()

      self.redirect('/property?id=' + str(newlisting.key()))
    else:
      self.redirect(users.create_login_url(self.request.uri))


class ProcessBidHandler(BaseRequestHandler):
  """  Processes the input of a bid."""

  def get(self):
    logging.info('Visiting the ProcessBidHandler via get. Bad.')
    self.redirect("/")

  def post(self):
    """ Post method to accept Bid data."""
    logging.info('Visiting the ProcessBidHandler via post. Good.')
    user = users.get_current_user()

    if user:
      listing = ListingModel.get(self.request.get('key'))
      bidamount = int(self.request.get('bid'))
      if not listing.listingOwner = user:
        newbid = BidHistoryModel(listing=listing, bid=bidamount, bidder=user)
        newbid.put()

        currentMaxBid = listing.maxBid
        if bidamount > currentMaxBid:
          listing.maxBid = int(bidamount)
          listing.currentBid = (currentMaxBid + 1)
          listing.currentWinningBidderNickname = user.nickname()
          listing.numberOfBids += 1
        elif bidamount == currentMaxBid:
          listing.currentBid = currentMaxBid
          listing.numberOfBids += 1
        else:
          listing.currentBid = int(bidamount) + 1
          listing.numberOfBids += 1
        listing.put()
        self.redirect('/property?id=' + str(listing.key()))
      else:
        self.error(403)
        return
    else:
      self.redirect(users.create_login_url(self.request.uri))


class ProcessEndNowHandler(BaseRequestHandler):
  """  Processes the input of an EndNow request."""

  def get(self):
    logging.info('Visiting the ProcessEndNowHandler via get. Bad.')
    self.redirect("/")

  def post(self):
    """ Post method to accept End Now."""
    logging.info('Visiting the ProcessEndNowHandler via post. Good.')
    user = users.get_current_user()

    if user:

	  self.generate('.html', {
	    #'listings': query,
      })
    else:
      self.redirect(users.create_login_url(self.request.uri))


class DisplayCreateListingPageHandler(BaseRequestHandler):
  """  Generates the Create Listiing Page."""

  def get(self):
    logging.info('Visiting the CreateListingPage')
    user = users.get_current_user()

    if user:
      self.generate('createlisting.html', {
        #'listings': query,
      })
    else:
      self.redirect(users.create_login_url(self.request.uri))


class PropertyPageHandler(BaseRequestHandler):
  """  Generates a Listiing Page."""

  def get(self):
    logging.info('Visiting a ListingPage')
    entry = ListingModel.get(self.request.get('id'))
    if not entry:
      self.error(403)
      return
    else:
      self.generate('property.html', {
        'listing': entry,
      })


class SupportPageHandler(BaseRequestHandler):
  """ Generates the support page.

  """
  def get(self):
   logging.info('Visiting the support page')
   self.generate('support.html', {
     #'title': 'Getting Started',
   })


class AboutPageHandler(BaseRequestHandler):
  """ Generates the about page.

  """
  def get(self):
   logging.info('Visiting the about page')
   self.generate('about.html', {
     #'title': 'Getting Started',
   })


class OwnersPageHandler(BaseRequestHandler):
  """ Generates the owners page.

  """
  def get(self):
   logging.info('Visiting the owners page')
   self.generate('owners.html', {
     #'title': 'Getting Started',
   })


class RentersPageHandler(BaseRequestHandler):
  """ Generates the renters page.

  """
  def get(self):
    logging.info('Visiting the renters page')
    self.generate('renters.html', {
      #'title': 'Getting Started',
    })
    
    
class SupportThanksPageHandler(BaseRequestHandler):
  """ Generates the thanks for submitting your support question page.

  """
  def get(self):
    logging.info('Visiting the SupportThankspage')
    self.generate('supportthanks.html', {
      #'title': 'Getting Started',
    })



class SupportSubmissionHandler(BaseRequestHandler):
  """ Processes a support request

  """
  def get(self):
    logging.info('Visiting the SupportSubmissionHandler via get. Bad.')
    self.redirect("/")

  def post(self):
    """ Post method to SupportSubmissionHandler."""
    logging.info('Visiting the SupportSubmissionHandler via post. Good.')
    mail_admin = 'wferrell@gmail.com' # Pull this code out when posting.
    subject = 'AptAuction -- Support Question for Lane'
    mail.send_mail_to_admins(sender=mail_admin,
                               subject=subject,
                               body=self.request)
    self.redirect("/supportthanks")


# Map URLs to our RequestHandler classes above
_APTAUCTION_URLS = [
# after each URL map we list the html template that is displayed
   ('/', HomePageHandler), #home.html
   ('/index', HomePageHandler), #home.html
   ('/index.html', HomePageHandler), #home.html
   ('/createlisting', DisplayCreateListingPageHandler), #createlisting.html
   ('/createlistingsubmit', ProcessCreateListingHandler),
   ('/myaccount', MyAccountPageHandler), #myaccount.html
   ('/listings', ShowAllListingsPageHandler), #listings.html
   ('/bid', ProcessBidHandler),
   ('/property', PropertyPageHandler), #property.html
   ('/home', HomePageHandler), #home.html
   ('/about', AboutPageHandler), #about.html
   ('/owners', OwnersPageHandler), #owners.html
   ('/renters', RentersPageHandler), #renters.html
   ('/support', SupportPageHandler), #support.html
   ('/supportsend', SupportSubmissionHandler),
   ('/supportthanks', SupportThanksPageHandler), #supportthanks.html
   ('/.*$', HomePageHandler), #home.html
]


def main():
  application = webapp.WSGIApplication(_APTAUCTION_URLS, debug=_DEBUG)
  run_wsgi_app(application)

if __name__ == '__main__':
  main()
