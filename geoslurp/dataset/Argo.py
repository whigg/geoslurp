# This file is part of geoslurp.
# geoslurp is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.

# geoslurp is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with Frommle; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

# Author Roelof Rietbroek (roelof@geod.uni-bonn.de), 2018

from geoslurp.dataset import DataSet
from geoslurp.datapull.ftp import Crawler as ftpCrawler
from geoslurp.datapull.ftp import Uri as ftpUri
from geoslurp.datapull import findFiles
from geoslurp.datapull import UriFile
from geoalchemy2.types import Geography
from geoalchemy2.elements import WKBElement
from sqlalchemy import Column,Integer,String, Boolean
from sqlalchemy.dialects.postgresql import TIMESTAMP, JSONB
from sqlalchemy import MetaData
from netCDF4 import Dataset as ncDset
from osgeo import ogr
from datetime import datetime,timedelta
from queue import Queue
import gzip as gz
import logging
import os
import re
# To do:  etract meta information with a threadpool
#from concurrent.futures import ThreadPoolExecutor

from sqlalchemy.ext.declarative import declarative_base


class ArgoftpCrawler(ftpCrawler):
    """Adapted ftpcrawler class to get speedier (concurrent) downloads for argo files
    Takes advantage of the argo index files"""
    def uris(self):
        """This creates a list of _prof.nc files without having to list subdirectories"""

        buf=ftpUri(self.rooturl+"ar_index_global_meta.txt.gz").buffer()
        regex=re.compile('^([a-z]+/[0-9]+/)([0-9]+_meta.nc),[0-9]+,.{2},([0-9]+)')
        for ln in gz.decompress(buf.getvalue()).splitlines():
            mtch=regex.search(ln.decode('utf-8'))
            if not re.match(self.pattern,ln.decode('utf-8')):
                continue
            if mtch:
                subdir=mtch.group(1)
                fname=mtch.group(2).replace('meta','prof')
                t=datetime.strptime(mtch.group(3),"%Y%m%d%H%M%S")
                yield ftpUri(os.path.join(self.rooturl,'dac',subdir,fname),lastmod=t,subdirs=subdir)


#create a custom exception which describes netcdf datasets with dimensions of zero length
class ZeroDimException(Exception):
    pass

# A declarative base which can be used to create database tables

OceanObsTBase=declarative_base(metadata=MetaData(schema='oceanobs'))

# Setup the postgres table

geoPointtype = Geography(geometry_type="POINTZ", srid='4326', spatial_index=True,dimension=3)

class ArgoTable(OceanObsTBase):
    """Defines the Argo PostgreSQL table"""
    __tablename__='argo'
    id=Column(Integer,primary_key=True)
    datacenter=Column(String)
    lastupdate=Column(TIMESTAMP)
    tprofile=Column(TIMESTAMP)
    tlocation=Column(TIMESTAMP)
    wmoid=Column(Integer)
    cycle=Column(Integer)
    uri=Column(String, index=True)
    mode=Column(String,index=True)
    profnr=Column(Integer)
    ascending=Column(Boolean)
    geom=Column(geoPointtype)
    data=Column(JSONB)


def ncStr(ncelem):
    """extracts a utf-8 encoded string from a  netcdf character variable and strips trailing junk"""
    return b"".join(ncelem).decode('utf-8').strip("\0")

def argoMetaExtractor(uri,cachedir=False):
    """Extract meta information as a drictionary from  an argo floats
    Each registered profile gets a separate entry"""

    meta=[]
    try:
        url=uri.url
        ncArgo=ncDset(url)


        logging.info("Extracting meta info from: %s"%(url))

        # Get reference time
        t0=datetime.strptime(b"".join(ncArgo["REFERENCE_DATE_TIME"][:]).decode("utf-8"),"%Y%m%d%H%M%S")
        for iprof in range(ncArgo.dimensions["N_PROF"].size):
            # geographical location
            geoLoc=ogr.Geometry(ogr.wkbPoint)
            geoLoc.AddPoint(float(ncArgo["LONGITUDE"][iprof]), float(ncArgo["LATITUDE"][iprof]))
            # time point
            tprof=t0+timedelta(days=float(ncArgo["JULD"][iprof].data))
            tloc=t0+timedelta(days=float(ncArgo["JULD_LOCATION"][iprof].data))
            cycle=int(ncArgo["CYCLE_NUMBER"][iprof].data)
            datacenter=ncStr(ncArgo["DATA_CENTRE"][iprof])
            direction=bool(ncArgo["DIRECTION"][iprof].data == b"A")
            wmoid=int(ncStr(ncArgo["PLATFORM_NUMBER"][iprof]))
            mode=ncStr(ncArgo["DATA_MODE"][:])[iprof]
            meta.append({"datacenter":datacenter,"lastupdate":uri.lastmod, "tprofile":tprof,
                         "tlocation":tloc, "wmoid":wmoid, "cycle":cycle , "uri":url,
                         "mode":mode, "profnr":iprof, "ascending":direction,
                         "geom":WKBElement(geoLoc.ExportToWkb(),srid=4326,extended=True),"data":{}})
    except ZeroDimException as e:
        raise RuntimeWarning(str(e)+", skipping")
    except Exception as e:
        raise RuntimeWarning("Cannot extract meta information from "+ url+ str(e))

    return meta


class Argo(DataSet):
    """Argo table"""
    __version__=(0,0,0)
    table=ArgoTable
    def __init__(self,scheme):
        super().__init__(scheme)
        self.updated=[]
        # Create table if it doesn't exist
        # import pdb;pdb.set_trace()
        OceanObsTBase.metadata.create_all(self.scheme.db.dbeng, checkfirst=True)
        self._uriqueue=Queue(maxsize=300)
        self._killUpdate=False
        self.thrd=None
        #set Argo mirrors and datacenters
        #add thredds catalogs when non-existent
        # if 'thredds' not in self._inventData:
        #     catalogs= ["http://tds0.ifremer.fr/thredds/catalog/CORIOLIS-ARGO-GDAC-OBS/", "https://data.nodc.noaa.gov/thredds/catalog/argo/gdac/"]
            # self._inventData['thredds']=[]
            # filt=ThreddsFilter("catalogRef")
            # followfilt=ThreddsFilter("dataset")
            # for cat in catalogs:
            #     crwl=Crawler(cat+'catalog.xml',filter=filt,followfilter=followfilt)
            #     servdict=crwl.services._asdict()
            #     servdict['centers']=[getAttrib(el,'title') for el in crwl.xmlitems()]
            #     self._inventData['thredds'].append(servdict)
        if 'resume' not in self._inventData:
            self._inventData["resume"]={}

    def pull(self,center=None,mirror=0):
        """ Pulls the combined *_prof.nc files from the ftp server
        :param center (string): only pull data from a specific datacenter
        :param mirror (0 or 1): use ifremer (0) or usgodae (1) mirror
        """
        ftpmirrors=["ftp://ftp.ifremer.fr/ifremer/argo/","ftp://usgodae.org/pub/outgoing/argo/"]

        #since crawling thought the ftp directories takes relatively much time we're going to speed up
        if center:
            ftpcrwl=ArgoftpCrawler(ftpmirrors[mirror],center)
        else:
            ftpcrwl=ArgoftpCrawler(ftpmirrors[mirror])
        self.updated=ftpcrwl.parallelDownload(self.dataDir(),check=True,maxconn=10,continueonError=True)


    def register(self,center=None):
        """register downloaded commbined prof files"""

        #create a list of files which need to be (re)registered
        if self.updated:
            files=self.updated
        else:
            files=[UriFile(file) for file in findFiles(self.dataDir(),'.*nc')]

        #loop over files
        for uri in files:
            if center and not re.search(center,uri.url):
                continue

            urilike=uri.url

            if not self.uriNeedsUpdate(urilike,uri.lastmod):
                continue
            for meta in argoMetaExtractor(uri):
                self.addEntry(meta)

        self._inventData["lastupdate"]=datetime.now().isoformat()
        self._inventData["version"]=self.__version__
        self.updateInvent()

        self.ses.commit()



    # def thredssregister(self,center=None,mirror=1,resume=False):
    #     """Extracts metadata from the float and registers it in the database
    #         :param center: specifies the processing center to screen (default takes all available)
    #             currently avalaible are: aoml, bodc, coriolis, csio, csiro, incois, jma, kma, kordi, meds, nmdis
    #         :param mirror: use mirror 0: https://tds0.ifremer.fr (default) or mirror 1: https://data.nodc.noaa.gov
    #         :param resume: boolean: resume indexing from last attempt
    #     """
    #
    #     #first retrieve a list of catalogrefs  (i.e. datacenters)
    #     # make a list of all available centers
    #     if center:
    #         #only consider a specific center
    #         if center not in self._inventData['thredds'][mirror]['centers']:
    #             raise RuntimeError('Datacenter not found')
    #         centers=[center]
    #     else:
    #         centers=self._inventData['thredds'][mirror]['centers']
    #
    #     if resume:
    #         try:
    #             #make a list of remaining centers
    #             cntr=self._inventData["resume"]["center"]
    #             floatid=self._inventData["resume"]["floatid"]
    #             centers=centers[centers.index(cntr):]
    #             resumefilt=ThreddsFilter("catalogRef",attr="ID",regex=".*"+cntr+"/"+floatid+".*")
    #         except Exception as e:
    #             logging.warning("no resume information found, so starting from the beginning")
    #             pass
    #     else:
    #         resumefilt=None
    #
    #     for cent in centers:
    #         self._inventData["resume"]["center"]=cent
    #         #loop over all processing centers
    #         logging.info("Getting catalog of processing center %s"%(cent))
    #         #determine center catalog url
    #         catalogurl=self._inventData['thredds'][mirror]['baseurl']+self._inventData['thredds'][mirror]['catalog']+cent+'/catalog.xml'
    #         filt = ThreddsFilter("dataset", attr="urlPath", regex=".*_prof.nc")
    #
    #         followf=ThreddsFilter("catalogRef",attr="ID",regex='.*'+cent+'(?!\/[0-9]+\/profiles)',).OR("dataset")
    #         # let's start a thread which will start quering the threddsserver and queues jobs
    #         crwl=Crawler(catalogurl, filter=filt,followfilter=followf)
    #         if(resume):
    #             #set a resume point but only follow datasets (i.e. don't download subcatalogues)
    #             crwl.setResumePoint(resumefilt,followfilt=ThreddsFilter("dataset"))
    #
    #         self.thrd=Thread(target=self.pullWorker, kwargs={"conn":crwl})
    #         self.thrd.start()
    #
    #         #create a dedicated database session
    #         ses=self.scheme.db.Session()
    #         i=0
    #         while not self._killUpdate:
    #             try:
    #                 uri=self._uriqueue.get()
    #                 if uri == None:
    #                     # done
    #                     break
    #
    #                 # Check whether entries already exists in the database which is up to date
    #                 try:
    #                     noupdate=False
    #                     qResults=ses.query(self.table).filter(self.table.uri.like('%'+uri.suburl+'%'))
    #                     for qres in qResults:
    #                         if qres.lastupdate >= uri.lastmod:
    #                             logging.info("No Update needed, skipping %s"%(uri.suburl))
    #                             self._uriqueue.task_done()
    #                             noupdate=True
    #                         else:
    #                             noupdate=False
    #                             #delete the entries which need updating
    #                             # ses.query(ArgoTable).filter(ArgoTable.uri.like('%'+uri.suburl+'%')).delete()
    #                             ses.delete(qres)
    #
    #                     if noupdate:
    #                         continue
    #                 except:
    #                     # Fine no entries found
    #                     pass
    #
    #                 for metadict in argoMetaExtractor(uri,self.cacheDir(os.path.dirname(uri.suburl))):
    #                     entry=self.table(**metadict)
    #                     ses.add(entry)
    #                     if i > 10:
    #                         # commit every so many rows
    #                         ses.commit()
    #                         #extract the current floatid (needed for storing resume info)
    #                         self._inventData["resume"]["floatid"]=uri.url.split("/")[-3]
    #                         i=0
    #                     else:
    #                         i+=1
    #                 self._uriqueue.task_done()
    #             except Exception as e2:
    #                 # let the threddscrawler come to a graceful halt
    #                self.halt()
    #
    #         ses.commit()
    #         #also update the inventory
    #         self._inventData["lastupdate"]=datetime.now().isoformat()
    #         self._inventData["version"]=self.__version__
    #         if cent not in self._inventData['thredds'][mirror]['centers']:
    #             self._inventData['centers'].append(cent)
    #
    #
    #         self.updateInvent()
    #         self.thrd.join()
    #         #set resume to false after sucessfully processing one center
    #         resume=False


    def halt(self):
        logging.error("Stopping update")
        self._killUpdate=True
        # indicate a done task n the queue in order to allow the pullWorker thread to stop gracefully
        #empty queue
        while not self._uriqueue.empty():
            self._uriqueue.get()
            self._uriqueue.task_done()
        #also synchronize inventory info (e.g. resume information)
        self.updateInvent()
        raise RuntimeWarning("Argo dataset processing stopped")

    def pullWorker(self,conn):
        """ Pulls valid opendap URI's from a thredds server and queue them"""

        for uri in conn.uris():
            logging.info("queuing %s",uri.url)
            self._uriqueue.put(uri)
            if self._killUpdate:
                logging.warning("Pulling of Argo URI's stopped")
                return
        #signal the end of the queue by adding a none
        self._uriqueue.put(None)

