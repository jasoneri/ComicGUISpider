import DefaultTheme from 'vitepress/theme'
import Layout from './Layout.vue'
import './style.css'
import type { App } from 'vue'
import HomeDemoVideo from './components/HomeDemoVideo.vue'

export default {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }: { app: App }) {
    app.component('HomeDemoVideo', HomeDemoVideo)
  }
}