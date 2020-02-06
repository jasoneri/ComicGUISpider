# m90h_comic_spider
 python3.7, scrapy, pyqt5, win10x64
 
此代码仅为学习使用

功能：搜索漫画，多选下载到本地，免去一些网站一页一页加载看<br>
-----------------------------------------------
程序内置帮助说明，点击说明查看即可，压缩包解压即可用，点它下载→   [ (*￣ω￣)](https://pan.baidu.com/s/1dHmGbrTehOqcoqAgcGpp9Q) 验证码【fnf3】

PS：setting.txt、scrapy.cfg和exe程序要放一起！

scrapy.cfg [SHA1]: 374afa103c2c94be92d6bf3f09fdbc39d36fec98  <br>
scrapy.cfg [MD5]: 139676f1785e3af51666538981629a24  <br>
exe [SHA1]: 43e60a70d5a327b1eb9d8c2ff777e9452bb5523d  <br>
exe [MD5]: 69e9b611d51e432c4301fc3049f4925a  <br>

    （ MD5校验：Ctrl+Alt+C开管理台→ certutil -hashfile 私人路径/ComicSpider.exe MD5

可在exe所在目录下创建【 setting.txt 】更改IP或下载目录
-----------------------------------------------

>### 1、设置或更改代理IP：

(log目录下scrapy日志（用过才有）看看响应码如果非200而关闭，自行百度免费代理IP将下面这段的IP替换后扔进去【 setting.txt 
<br>但代理IP可能很快失效，善查log日志排错 )

IP示例： 192.168.1.1：9999 （ 必须有端口 ）

------------------------------------------
    proxies=['aaa.aaa.aaa.aaa:61234',
             'bbb.bbb.bbb.bbb:80',
             'ccc.ccc.ccc.ccc:8080',
             'ddd.ddd.ddd.ddd:808',
             'eee.eee.eee.eee:8080']
------------------------------------------


>### 2、更改默认下载目录：


将示例中的目录更改后整段扔进去【 setting.txt 】：

------------------------------------------
    path='D:\comic'
------------------------------------------

（ ‘D:\comic’ 改为你的目录，不设的话就是它 ) （ <s>相对路径难搞，吐血</s> ）


------------------------------------------
>【 bug记录 】


+ 1、目前kuku网站的部分可能下不了，目测网站框架更新多结构并存（ 他网的漫画名一时还有乱七八糟符号 ……囧 <br>etc…………

<s> 后续鸽子：加首页图显示<br>把ehentai加上</s>
