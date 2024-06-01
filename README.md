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

## 二、配置setting.txt

### 1、更改默认下载目录：

找个空行，在<>中放入自定义下载目录，不设默认在 D:\comic  

```
    <D:\comic>
```

### 2、代理IP功能：

IP示例： 192.168.1.1:9999 （ IP:端口 ） 可一次扔几个，用空格或回车隔开就好

```
    aaa.aaa.aaa.aaa:61234
    bbb.bbb.bbb.bbb:80
```

### 3、排错功能： 

出错可先往setting.txt扔一个大写的 DEBUG 重开，更改日志等级  
后台有运行过有log目录，GUI记录界面操作记录默认为INFO，scrapy默认为WARNING  
<br>
------

>## 【 bug记录 】

1. 缺页问题：少见，看了下好像是懒加载（？这个有无影响有待商榷）和叠层
   图的标签有叠两层实际只有一层可以响应，目前只通配了一层所以可能性缺页，呃……这个放放以后再想  

