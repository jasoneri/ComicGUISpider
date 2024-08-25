#!/usr/bin/python
# -*- coding: utf-8 -*-
ENV = "简中环境"


# GUI
class GUI:
    DESC1 = "1、首次使用请查阅`CGS-使用说明.exe`(内容与`scripts/README.md`一样)，内有配置/GUI视频使用指南等说明<br>"
    DESC2 = "2、除非版本更新，一般bug修复/功能更新等，用户运行`CGS-更新.exe`即可<br>"
    DESC3 = "3、在 github wiki 上也有记录 Q & A，可以先查阅看能否解决疑惑"
    DESC4 = " 若有其他问题到群反映/提issue<br>"

    BrowserWindow_ensure_warning = "需要返回选择页，并确保有选择的情况下使用"

    toolBox_warning = "仅当常规漫画网站能使用工具箱功能"
    wnacg_run_slow_in_cn_tip = "wancg 国内源有点慢哦，半分钟没出列表时，看看 `scripts/log/scrapy.log` 是不是报错了 <br>" + \
                               "网络问题一般重启就好了，数次均无效的话 加群反映/提issue<br>"
    checkisopen_text_change = "现在点击立刻打开存储目录"
    checkisopen_status_tip = "勾选状态下完成后也会自动打开目录的"
    textbrowser_load_if_http = (u'<b><font size="5"><br>  内置预览：点击右下 "点我预览" </font></b> 或者 '
                                u'<a href="%s" ><b style="font-size:20px;">浏览器查看结果</b></a>')
    WorkThread_finish_flag = "完成任务"  # related to SPIDER.close_success
    copymaga_page_status_tip = "拷贝漫画的翻页数使用的offset/序号，一页30条，想翻到第3页就填60(输出60-89)，类推"

    class ToolMenu:
        action1 = "显示已阅最新话数记录"
        action2 = "整合章节并移至web目录"
        action2_warning = "未配合[comic_viewer]项目产生记录文件[%s]，\n功能无法正常使用"


# website
class EHentai:
    PROXIES_NEED = True
    PROXIES_NOT_SET = "访问 e-hentai 必须代理"


# backend (spider/scrapy)
class SPIDER:
    # basecomicspider
    class SayToGui:
        exp_txt = f"""<br>{'{:=^80}'.format('message')}<br>请于【 输入序号 】框输入要选的序号  """
        exp_preview = "<br>进预览页面能直接点击封面进行多选，与【 输入序号 】框的序号相叠加"
        exp_replace_keyword = '<br>请于'
        TextBrowser_error = """选择{1}步骤时错误的输入：{0}<br> {2}"""  # discarded
        frame_book_print_extra = " →_→ 鼠标移到序号栏有教输入规则<br>"
        frame_book_print_retry_tip = "什么意思？唔……就是你搜的在放✈(飞机)，点击retry重开"
        frame_section_print_extra = " ←_← 点击【开始爬取！】 <br>"

    search_url_head_NotImplementedError = '需要自定义搜索网址'
    parse_step = '漫画'  # not use
    parse_sec_step = '章节'  # not use
    parse_sec_not_match = '没匹配到结果'
    parse_sec_selected = '所选序号'
    parse_sec_now_start_crawl_desc = "现在开始爬取《%s》章节"
    close_success = "后台完成任务了"
    close_backend_error = "后台挂了，若非自己取消可进行如下操作"
    close_check_log_guide1 = '1、打开下方给的日志文件，应该能解决大部分疑惑<br>'
    close_check_log_guide2 = '2、第1步不足以解惑的话，重启(retry)程序 > 更改配置 > 日志等级设为`DEBUG` > 重复引发出错的步骤<br>'
    close_check_log_guide3 = '3、第2步得出的日志仍不以解惑的话，请到群反映或提issue<br>'

    # spiders

    # pipelines
    ERO_BOOK_FOLDER = "本子"
    PAGE_NAMING = '第%s页.jpg'


# folder of deploy
class Updater:
    ver_check = "检查版本中"
    ver_file_not_exist = "没有version文件，准备初始化"
    check_refresh_code = "检查需要更新的代码"
    code_downloading = "下载代码文件中"
    finish = "更新完毕"
    not_pkg_markdown = "当前环境无法使用此功能，需要重新下载绿色安装包"
    first_init = "首次使用更新，初始化覆盖中"
    refreshing_code = "更新代码中"
    code_is_latest = "代码已是最新.. 若有其他问题向群里反映"
    env_covering = "环境补充中"
    env_trigger_flag = "检测到需要补充环境"
    env_is_latest = "环境已是最新"
