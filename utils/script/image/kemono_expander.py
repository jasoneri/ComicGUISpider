#!/usr/bin/python
# -*- coding: utf-8 -*-
import re
import pandas as pd


class Artists:
    @staticmethod
    def keihh(posts):
        """patreon/user/
        naming hobby: title, title(v2), title(v3)...
        """
        df = pd.DataFrame(posts)

        df['BaseName'] = df['title'].apply(lambda x: re.sub(r'\(.*\)', '', x))
        df['Version'] = df['title'].apply(lambda x: re.search(r'\((v\d+)\)', x))
        df['Version'] = df['Version'].apply(lambda x: x.group(1) if x else 'v0')

        df['title'] = df['title'].apply(lambda x: re.sub(r'([|:<>?*"\\/])', '', x))
        # 找到每个标题的最新版本
        latest_versions = df.loc[df.groupby('BaseName')['Version'].idxmax()]

        del latest_versions['BaseName']
        del latest_versions['Version']
        dic_posts = latest_versions.to_dict(orient='records')
        return dic_posts

    @staticmethod
    def a5p74od3(posts):
        posts = list(filter(lambda post: 'PSD' not in post['title'], posts))
        return posts

    @staticmethod
    def Gsusart2222(posts):
        return Artists.normal(posts)

    @staticmethod
    def normal(posts):
        """默认使用，统一将目录命名的非法字符装换成`-`"""
        for post in posts:
            post['title'] = re.sub(r'([|:<>?*"\\/])', '-', post['title'])
        return posts
