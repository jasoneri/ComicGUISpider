import DefaultTheme from 'vitepress/theme'
import Layout from './Layout.vue'
import './style.css'
import type { App } from 'vue'
import HomeDemoVideo from './components/HomeDemoVideo.vue'
import TimelineWidget from '../components/timeline/TimelineWidget.vue'

export default {
  extends: DefaultTheme,
  Layout,
  enhanceApp({ app }: { app: App }) {
    app.component('HomeDemoVideo', HomeDemoVideo)
    app.component('TimelineWidget', TimelineWidget)
  }
}