# m90h_comic_spider
 python3.7, scrapy win10x64

此代码仅为学习使用

+ ( now exe & zip didn't contain new func，as future will make GUI instead )

程序使用方法参考![【image】](https://github.com/jasoneri/ComicSpider/blob/master/1%E5%9B%BE%E6%B5%81%E7%A4%BA%E4%BE%8B.jpg) or 压缩包内【1图流实例.jpg】

setting.txt、scrapy.cfg和exe程序要放一起，切记

可在exe所在目录下创建【 setting.txt 】更改IP或下载地址
-
+ 1、设置或更改代理IP：
(响应失败多数换IP能破，要求5个左右，可从此网找几个用 【 https://www.kuaidaili.com/free 】 或自行百度免费代理IP)

IP示例： 192.168.1.1：9999 （ 必须有端口 ）

------------------------------------------
    proxies=['aaa.aaa.aaa.aaa:61234',
             'bbb.bbb.bbb.bbb:80',
             'ccc.ccc.ccc.ccc:8080',
             'ddd.ddd.ddd.ddd:808',
             'eee.eee.eee.eee:8080']
------------------------------------------


+ 2、本文件目录下的【 setting.txt 】设置或更改下载地址：


将示例中的目录更改后整段扔进去setting.txt：（目录需符合文件命名规则）

------------------------------------------
    path='D:\comic'
------------------------------------------

（可不设，默认下载地址为上述地址）
