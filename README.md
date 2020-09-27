# ComicSpider
![](https://img.shields.io/badge/Python-3.7%2B-brightgreen.svg?style=social) ![](https://img.shields.io/badge/Mode-GUI+Scrapy-blue.svg?colorA=abcdef)  
目前是一个交互式下漫画的项目  

## 更新
+ V1.3 | 2020-09-13  
1、加了特殊网站…  ……

## 一、简述  
![EXE简图](https://github.com/jasoneri/ComicSpider/blob/GUI/GUI/exe.jpg)

程序内置使用说明，点击说明按钮跟着按即可，此链下载zip →  [http://…(*￣ω￣)…](https://pan.baidu.com/s/1cDeHa9SB-RFbjQP3hpH2tw) 提取码:z8si   
PS：配置文件setting.txt，跟EXE放一起就生效，可以不放  

zip [SHA1]:  95a6c822d2422f07eb084b1f330e73f6198ecb75   
zip [MD5]: 3709fbd9a8a5ebbfcadd9c41b0ee19c3   


## 二、配置setting.txt

### 1、更改默认下载目录：

找个空行，在<>中放入自定义下载目录，不设默认在 D:\comic  

```
    <D:\comic>
```

### 2、代理IP功能：

IP示例： 192.168.1.1：9999 （ IP:端口 ） 可一次扔几个，用空格或回车隔开就好

```
    aaa.aaa.aaa.aaa:61234
    bbb.bbb.bbb.bbb:80
```

### 3、排错功能：   

出错可先往setting.txt扔一个大写的 DEBUG 重开，更改日志等级  
后台有运行过有log目录，GUI记录界面操作记录默认为INFO，scrapy默认为WARNING   


------

>## 【 bug记录 】


+ 1、缺页问题：少见，在第三个网站里某些页面会出现  
观察发现原因在于每一张图有两层叠起来而其实可以下载的只有其中一层，所以下到本地就各种缺页，呃……这个放放以后再想  

+ 2、retry部分搞不好有堆积内存问题，留了个脚本清内存 

