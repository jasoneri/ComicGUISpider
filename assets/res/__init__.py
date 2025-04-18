#!/usr/bin/python
# -*- coding: utf-8 -*-
import gettext
import pathlib
import locale
"""usage of `<br>`：
    1. 一行话禁止加 `br` ，换行在 `self.say()` 前解决;
    2. 多行的一段话可在最后加 `br` ，禁止在段落起始处加 `br`
    
    1. forbid the use of `br` in one line, solve line break before `self.say()`;
    2. add `br` at the end of a paragraph with multiple lines, forbid the use of `br` at the beginning of a paragraph
"""


def getUserLanguage():
    """corresponds to RFC 1766"""
    sys_lang, _ = locale.getlocale()
    match sys_lang.split('_')[0]:
        case 'Chinese (Simplified)':
            return 'zh-CN'
        case _:
            return 'en-US'

_path = pathlib.Path(__file__).parent
lang = getUserLanguage()
# lang = 'en-US'

gettext.bindtextdomain('res', str(_path / 'locale'))
gettext.textdomain('res')

try:
    _translation = gettext.translation('res', str(_path / 'locale'), languages=[lang], fallback=False)
    _ = _translation.gettext
except FileNotFoundError as e:
    print(str(e))
    _ = gettext.gettext


# GUI
class GUI:
    DESC1 = _('GUI.DESC1')
    DESC2 = _('GUI.DESC2')
    DESC_ELSE = _('GUI.DESC_ELSE')

    BrowserWindow_ensure_warning = _('GUI.BrowserWindow_ensure_warning')

    jm_bookid_support = _('GUI.jm_bookid_support')
    wnacg_run_slow_in_cn_tip = _('GUI.wnacg_run_slow_in_cn_tip')
    mangabz_desc = _('GUI.mangabz_desc')
    check_ehetai = _('GUI.check_ehetai')
    check_mangabz = _('GUI.check_mangabz')
    checkisopen_text_change = _('GUI.checkisopen_text_change')
    checkisopen_status_tip = _('GUI.checkisopen_status_tip')
    ACCESS_FAIL = _('GUI.ACCESS_FAIL')
    cookies_copy_err = _('GUI.cookies_copy_err')
    copied_tip = _('GUI.copied_tip')
    ClipTasksPartFail = _('GUI.ClipTasksPartFail')
    textbrowser_load_if_http = _('GUI.textbrowser_load_if_http')
    WorkThread_finish_flag = _('GUI.WorkThread_finish_flag')
    WorkThread_empty_flag = _('GUI.WorkThread_empty_flag')
    copymaga_tips = _('GUI.copymaga_tips')
    copymaga_page_status_tip = _('GUI.copymaga_page_status_tip')
    global_err_hook = _('GUI.global_err_hook')
    input_format_err = _('GUI.input_format_err')
    reboot_tip = _('GUI.reboot_tip')

    class ToolMenu:
        action1 = _('GUI.ToolMenu.action1')
        action2 = _('GUI.ToolMenu.action2')
        action2_warning = _('GUI.ToolMenu.action2_warning')
        action_ero1 = _('GUI.ToolMenu.action_ero1')
        clip_process_warning = _('GUI.ToolMenu.clip_process_warning')

    class Uic:
        chooseBoxDefault = _('GUI.Uic.chooseBoxDefault')
        searchinputPrefix = _('GUI.Uic.searchinputPrefix')
        chooseinputPrefix = _('GUI.Uic.chooseinputPrefix')
        next_btnDefaultText = _('GUI.Uic.next_btnDefaultText')
        checkisopenDefaultText = _('GUI.Uic.checkisopenDefaultText')
        chooseinputTip = _('GUI.Uic.chooseinputTip')
        chooseBoxToolTip = _('GUI.Uic.chooseBoxToolTip')
        previewBtnStatusTip = _('GUI.Uic.previewBtnStatusTip')
        progressBarStatusTip = _('GUI.Uic.progressBarStatusTip')
        
        sv_path_desc = _('GUI.Uic.sv_path_desc')
        sv_path_desc_tip = _('GUI.Uic.sv_path_desc_tip')
        menu_show_completer = _('GUI.Uic.menu_show_completer')
        menu_next_page = _('GUI.Uic.menu_next_page')
        menu_prev_page = _('GUI.Uic.menu_prev_page')
        
        confDia_labelLogLevel = _('GUI.Uic.confDia_labelLogLevel')
        confDia_labelDedup = _('GUI.Uic.confDia_labelDedup')
        confDia_labelAddUuid = _('GUI.Uic.confDia_labelAddUuid')
        confDia_labelProxy = _('GUI.Uic.confDia_labelProxy')
        confDia_labelMap = _('GUI.Uic.confDia_labelMap')
        confDia_labelPreset = _('GUI.Uic.confDia_labelPreset')
        confDia_labelClipDb = _('GUI.Uic.confDia_labelClipDb')
        confDia_labelClipNum = _('GUI.Uic.confDia_labelClipNum')
        confDia_descBtn = _('GUI.Uic.confDia_descBtn')
        confDia_updateBtn = _('GUI.Uic.confDia_updateBtn')
        confDia_updateDialog_stable = _('GUI.Uic.confDia_updateDialog_stable')
        confDia_updateDialog_dev = _('GUI.Uic.confDia_updateDialog_dev')
        confDia_supportBtn = _('GUI.Uic.confDia_supportBtn')
        confDia_promote_title = _('GUI.Uic.confDia_promote_title')
        confDia_promote_content = _('GUI.Uic.confDia_promote_content') 
        confDia_promote_url = _('GUI.Uic.confDia_promote_url')
        confDia_feedback_group = _('GUI.Uic.confDia_feedback_group')
        confDia_feedback_group_copied = _('GUI.Uic.confDia_feedback_group_copied')
        confDia_support_content = _('GUI.Uic.confDia_support_content')


# website
class EHentai:
    COOKIES_NOT_SET = _('EHentai.COOKIES_NOT_SET')
    ACCESS_FAIL = _('EHentai.ACCESS_FAIL')
    GUIDE = _('EHentai.GUIDE')
    JUMP_TIP = _('EHentai.JUMP_TIP')


# backend (spider/scrapy)
class SPIDER:
    # basecomicspider
    class SayToGui:
        exp_txt = _('SPIDER.SayToGui.exp_txt')
        exp_turn_page = _('SPIDER.SayToGui.exp_turn_page')
        exp_preview = _('SPIDER.SayToGui.exp_preview')
        exp_replace_keyword = _('SPIDER.SayToGui.exp_replace_keyword')
        TextBrowser_error = _('SPIDER.SayToGui.TextBrowser_error')
        frame_book_print_extra = _('SPIDER.SayToGui.frame_book_print_extra')
        frame_book_print_retry_tip = _('SPIDER.SayToGui.frame_book_print_retry_tip')
        frame_section_print_extra = _('SPIDER.SayToGui.frame_section_print_extra')

    search_url_head_NotImplementedError = _('SPIDER.search_url_head_NotImplementedError')
    choice_list_before_turn_page = _('SPIDER.choice_list_before_turn_page')
    parse_step = _('SPIDER.parse_step')
    parse_sec_step = _('SPIDER.parse_sec_step')
    parse_sec_not_match = _('SPIDER.parse_sec_not_match')
    parse_sec_selected = _('SPIDER.parse_sec_selected')
    parse_sec_now_start_crawl_desc = _('SPIDER.parse_sec_now_start_crawl_desc')
    page_less_than_one = _('SPIDER.page_less_than_one')

    finished_success = _('SPIDER.finished_success')
    finished_err = _('SPIDER.finished_err')
    finished_empty = _('SPIDER.finished_empty')
    close_backend_error = _('SPIDER.close_backend_error')
    close_check_log_guide1 = _('SPIDER.close_check_log_guide1')
    close_check_log_guide2 = _('SPIDER.close_check_log_guide2')
    close_check_log_guide3 = _('SPIDER.close_check_log_guide3')

    # spiders

    # pipelines
    ERO_BOOK_FOLDER = _('SPIDER.ERO_BOOK_FOLDER')
    PAGE_NAMING = _('SPIDER.PAGE_NAMING')

    # utils
    DOMAINS_INVALID = _('SPIDER.DOMAINS_INVALID')


# folder of deploy
class Updater:
    ver_check = _('Updater.ver_check')
    ver_file_not_exist = _('Updater.ver_file_not_exist')
    check_refresh_code = _('Updater.check_refresh_code')
    code_downloading = _('Updater.code_downloading')
    finish = _('Updater.finish')
    not_pkg_markdown = _('Updater.not_pkg_markdown')
    token_invalid_notification = _('Updater.token_invalid_notification')
    latest_code_overwriting = _('Updater.latest_code_overwriting')
    too_much_waiting_update = _('Updater.too_much_waiting_update')
    refreshing_code = _('Updater.refreshing_code')
    refresh_fail_retry = _('Updater.refresh_fail_retry')
    refresh_fail_retry_over_limit = _('Updater.refresh_fail_retry_over_limit')
    code_is_latest = _('Updater.code_is_latest')
    env_is_latest = _('Updater.env_is_latest')
    ver_local_latest = _('Updater.ver_local_latest')
    ver_check_fail = _('Updater.ver_check_fail')
    update_ensure = _('Updater.update_ensure')
    updated_success = _('Updater.updated_success')
    updated_fail = _('Updater.updated_fail')
