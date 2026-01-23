<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

const props = defineProps<{
  triggerMargin?: string
  concurrency?: number
}>()

const containerRef = ref<HTMLElement>()
let observer: IntersectionObserver | null = null

// 并发控制的图片加载函数
async function loadImagesWithConcurrency(images: HTMLImageElement[], limit: number = 3) {
  const loadImage = (img: HTMLImageElement): Promise<void> => {
    return new Promise((resolve, reject) => {
      const dataSrc = img.getAttribute('data-src')
      if (!dataSrc) {
        resolve()
        return
      }

      const tempImg = new Image()
      tempImg.onload = () => {
        img.src = dataSrc
        img.removeAttribute('data-src')
        resolve()
      }
      tempImg.onerror = () => {
        console.warn('Image load failed:', dataSrc)
        reject(new Error(`Failed to load: ${dataSrc}`))
      }
      tempImg.src = dataSrc
    })
  }

  const results: Promise<void>[] = []
  const executing: Promise<void>[] = []

  for (const img of images) {
    const promise = loadImage(img).catch(err => {
      console.warn('Image preload failed:', err)
    })
    results.push(promise)

    if (limit <= images.length) {
      const e: Promise<void> = promise.then(() => {
        executing.splice(executing.indexOf(e), 1)
      })
      executing.push(e)
      
      if (executing.length >= limit) {
        await Promise.race(executing)
      }
    }
  }

  await Promise.all(results)
}

onMounted(() => {
  observer = new IntersectionObserver(
    (entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          // 查找所有带 data-src 的图片
          const images = containerRef.value?.querySelectorAll('img[data-src]') as NodeListOf<HTMLImageElement>
          if (images && images.length > 0) {
            loadImagesWithConcurrency(
              Array.from(images),
              props.concurrency || 3
            )
          }
          observer?.disconnect()
        }
      })
    },
    { rootMargin: props.triggerMargin || '200px' }
  )
  
  if (containerRef.value) {
    observer.observe(containerRef.value)
  }
})

onUnmounted(() => {
  observer?.disconnect()
})
</script>

<template>
  <div ref="containerRef">
    <slot />
  </div>
</template>
