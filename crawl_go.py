# -*- coding: utf-8 -*-
# GUI
# from PyQt5.QtGui import QPixmap, QColor, QPalette, QBrush
from PyQt5.QtWidgets import QApplication
import GUI.material.material_ct

import PyQt5.sip
from PyQt5.QtCore import Qt, QSize, QMetaObject, QCoreApplication
from PyQt5.QtGui import QFont, QPixmap, QIcon, QCursor
from PyQt5.QtWidgets import QDialogButtonBox, QSizePolicy, QCommandLinkButton, QVBoxLayout, QFrame, QSpacerItem, \
    QLineEdit, QHBoxLayout, QCheckBox, QComboBox, QGroupBox, QTextBrowser, QWidget, QStatusBar, QProgressBar, \
    QPushButton, QToolButton, QTextEdit

# scrapy 打包相关
# import robotparser
import scrapy.spiderloader
import scrapy.statscollectors
import scrapy.logformatter
import scrapy.dupefilters
import scrapy.squeues

import scrapy.extensions.spiderstate
import scrapy.extensions.corestats
import scrapy.extensions.telnet
import scrapy.extensions.logstats
import scrapy.extensions.memusage
import scrapy.extensions.memdebug
import scrapy.extensions.feedexport
import scrapy.extensions.closespider
import scrapy.extensions.debug
import scrapy.extensions.httpcache
import scrapy.extensions.statsmailer
import scrapy.extensions.throttle

import scrapy.core.scheduler
import scrapy.core.engine
import scrapy.core.scraper
import scrapy.core.spidermw
import scrapy.core.downloader

import scrapy.downloadermiddlewares.stats
import scrapy.downloadermiddlewares.httpcache
import scrapy.downloadermiddlewares.cookies
import scrapy.downloadermiddlewares.useragent
import scrapy.downloadermiddlewares.httpproxy
import scrapy.downloadermiddlewares.ajaxcrawl
import scrapy.downloadermiddlewares.decompression
import scrapy.downloadermiddlewares.defaultheaders
import scrapy.downloadermiddlewares.downloadtimeout
import scrapy.downloadermiddlewares.httpauth
import scrapy.downloadermiddlewares.httpcompression
import scrapy.downloadermiddlewares.redirect
import scrapy.downloadermiddlewares.retry
import scrapy.downloadermiddlewares.robotstxt

import scrapy.spidermiddlewares.depth
import scrapy.spidermiddlewares.httperror
import scrapy.spidermiddlewares.offsite
import scrapy.spidermiddlewares.referer
import scrapy.spidermiddlewares.urllength

import scrapy.pipelines
import scrapy.core.downloader.handlers.datauri
import scrapy.core.downloader.handlers.file
import scrapy.core.downloader.handlers.ftp
import scrapy.core.downloader.handlers.s3
import scrapy.core.downloader.handlers.http
import scrapy.core.downloader.contextfactory
import scrapy.pipelines.images

# 自己项目用到的
from gui import SpiderGUI
import requests
import aiohttp
import lxml
import utils
import sys
from multiprocessing import freeze_support

# from multiprocessing.managers import RemoteError
# sys.setrecursionlimit(5000)

if __name__ == '__main__':
    freeze_support()
    app = QApplication(sys.argv)
    # app.setStyle("Fusion")
    ui = SpiderGUI()
    QApplication.processEvents()
    app.exec_()
