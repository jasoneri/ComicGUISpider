<script setup lang="ts">
import DefaultTheme from 'vitepress/theme'
import { useData, inBrowser } from 'vitepress'
import { watchEffect } from 'vue'
import Giscus from '@giscus/vue'

const { lang } = useData()
watchEffect(() => {
  if (inBrowser) {
    document.cookie = `nf_lang=${lang.value}; expires=Mon, 1 Jan 2030 00:00:00 UTC; path=/`
  }
})
</script>

<template>
  <DefaultTheme.Layout>
    <template #doc-after>
      <div class="giscus-wrapper">
        <Giscus
          id="giscus"
          repo="jasoneri/ComicGUISpider"
          repo-id="MDEwOlJlcG9zaXRvcnkyMjgzODc2OTU="
          category="Announcements"
          category-id="DIC_kwDODZzrb84ChuWn"
          mapping="title"
          term="Welcome to @giscus/vue!"
          reactions-enabled="1"
          emit-metadata="0"
          input-position="top"
          theme="preferred_color_scheme"
          lang="zh-CN"
          loading="lazy"
        />
      </div>
    </template>
  </DefaultTheme.Layout>
</template>

<style>
.giscus-wrapper {
  margin-top: 2rem;
  padding: 0 1rem;
}
</style>