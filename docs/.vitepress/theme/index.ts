import DefaultTheme from 'vitepress/theme'
import Layout from './Layout.vue'
import './style.css'
import type { App } from 'vue'
import ConcurrentImages from './components/ConcurrentImages.vue'

export default {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }: { app: App }) {
    app.component('ConcurrentImages', ConcurrentImages)
  }
}