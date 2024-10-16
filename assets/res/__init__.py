#!/usr/bin/python
# -*- coding: utf-8 -*-
ENV = "简中环境"


# GUI
class GUI:
    DESC1 = "1、首次使用请查阅`CGS-使用说明`(内容与`scripts/README.md`一样)，内有配置/GUI视频使用指南等说明<br>"
    DESC2 = "2、除非版本更新，一般bug修复/功能更新等，用户运行`CGS-更新`即可<br>"
    DESC3 = "3、在使用说明下方有问答记录 Q & A，可以先查阅看能否解决疑惑"
    DESC4 = " 若有其他问题/功能建议等到群反映/提issue<br>"

    BrowserWindow_ensure_warning = "需要返回选择页，并确保有选择的情况下使用"

    toolBox_warning = "仅当常规漫画网站能使用工具箱功能"
    jm_bookid_support = "支持多车号输入（检测十进制数字），例如`123456，654321，114514`（逗号分隔）<br>"
    wnacg_run_slow_in_cn_tip = "wancg 国内源偶尔会很慢，或者抽风，假如报错的话 <br>" + \
                               "网络问题如 [Errno 11001] / `ReadTimeout` 一般重启就好了，一直出现同一种错误的话 加群反映/提issue<br>"
    mangabz_desc = "Māngabz 使用源为iphone网页版，逆天章节只有数字，例如第一卷和第一话都是1，需要根据相邻章节自己鉴别"
    check_ehetai = "正在检测当前环境能否访问`exhentai`中..."
    check_mangabz = "正在检测当前环境能否访问`Māngabz`中..."
    checkisopen_text_change = "现在点击立刻打开存储目录"
    checkisopen_status_tip = "勾选状态下完成后也会自动打开目录的"
    ACCESS_FAIL = "当前`配置代理`或`全局代理`等环境 无法访问<br>请自行浏览器访问排查（软件尚不支持该网站无代理直连）<br>"
    textbrowser_load_if_http = (u'<b><font size="5" color="black"><br>  内置预览：点击右下 "点我预览" </font></b>'
                                u'<font color="black"> 或者 </font>'
                                u'<a href="%s" ><b style="font-size:20px;">浏览器查看结果</b></a>')
    WorkThread_finish_flag = "完成任务"  # related to SPIDER.close_success
    copymaga_page_status_tip = "拷贝漫画的翻页数使用的offset/序号，一页30条，想翻到第3页就填60(输出60-89)，类推"
    global_err_hook = "刚才操作导致 GUI 发生异常, 详细查阅 GUI 日志"

    class ToolMenu:
        action1 = "显示已阅最新话数记录"
        action2 = "整合章节并移至web目录"
        action2_warning = "未配合[comic_viewer]项目产生记录文件[%s]，\n功能无法正常使用"


# website
class EHentai:
    COOKIES_NOT_SET = "访问 exhentai 必须设置`eh_cookies`"
    ACCESS_FAIL = "当前`eh_cookies`或`配置代理`或`全局代理`等环境 无法访问<br>请自行浏览器访问排查（软件尚不支持无代理直连）"
    GUIDE = ("ehentai使用指引<br>1. 确保你有一个能访问`exhentai.org`的账号<br>"
             "2. (国内)确保你有一个可以使用的代理（不支持无代理直连）<br>"
             "3.1 基于第1点，配置需设置`eh_cookies`的值，cookies值生成参考`使用说明`里配置对应字段说明。<br>"
             "3.2 基于2，可使用全局代理（不建议）；或者配置代理，需要在此指引弹出前设置好，否则重启/retry生效。代理服务建议用v2rayN<br>")
    JUMP_TIP = "<br>ehentai页跳转情况特殊，没想好应用 暂时设限制取消`跳转页`功能<br>"


# backend (spider/scrapy)
class SPIDER:
    # basecomicspider
    class SayToGui:
        exp_txt = f"""<br>{'{:=^80}'.format('message')}<br>请于【 输入序号 】框输入要选的序号  """
        exp_turn_page = "<br>搜索框右侧为`翻页按钮组`，分别是 上一页/下一页/输入页数跳转"
        exp_preview = "<br>进预览页面能直接点击封面进行多选，与【 输入序号 】框的序号相叠加"
        exp_replace_keyword = "<br>请于"
        TextBrowser_error = """选择{1}步骤时错误的输入：{0}<br> {2}"""  # discarded
        frame_book_print_extra = " →_→ 鼠标移到序号栏有教输入规则<br>"
        frame_book_print_retry_tip = ("什么意思？唔……就是你搜的在放✈(飞机)<br>"
                                      "翻页的话就是这页之后没列表了，非翻页的话看看浏览器链接是否也没 / 重开换种姿势再搜")
        frame_section_print_extra = " ←_← 点击【开始爬取！】 <br>"

    search_url_head_NotImplementedError = '需要自定义搜索网址'
    choice_list_before_turn_page = "此前页面已选择(待结算)"
    parse_step = '漫画'  # not use
    parse_sec_step = '章节'  # not use
    parse_sec_not_match = '没匹配到结果'
    parse_sec_selected = '所选序号'
    parse_sec_now_start_crawl_desc = "现在开始爬取《%s》章节"
    page_less_than_one = "当前页数少于1，避免出错设置回第一页"
    close_success = "后台完成任务了"
    close_backend_error = "后台挂了，或没结果，或没进行选择！若非后两者可进行如下操作"
    close_check_log_guide1 = '1、打开下方的日志文件，查阅看有没开发者定义了的错误提示，或者是重试能解决的网络问题如 ReadTimeout<br>'
    close_check_log_guide2 = '2、第1步非网络问题的话，重启(retry)程序 > 更改配置 > 日志等级设为`DEBUG` > 重复引发出错的步骤<br>'
    close_check_log_guide3 = '3、第2步得出的日志同一种错误一直重复的话，请到群反映或提issue<br>'

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
    token_invalid_notification = ("[ 本地文件的token全部失效，当前将使用无状态去请求github api（受限60请求/小时）]\n"
                                  "下次使用更新会重新下载token文件，还是全部失效的话可截图告知开发者")
    latest_code_overwriting = "使用最新版本代码覆盖中"
    too_much_waiting_update = "检测到堆积过多待更新版本，将忽略更新消息直接拉至最新版本代码"
    refreshing_code = "更新代码中"
    refresh_fail_retry = "更新失败, 准备重试"
    refresh_fail_retry_over_limit = "是网络问题，重试更新即可。 若其他情况导致更新一直失败请截图发issue或找群反映"
    code_is_latest = "代码已是最新.. 若有其他问题向群里反映"
    env_covering = "环境补充中"
    env_trigger_flag = "检测到需要补充环境"
    env_is_latest = "环境已是最新"
