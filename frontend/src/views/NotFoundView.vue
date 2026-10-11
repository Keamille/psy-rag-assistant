<template>
  <div class="notfound">
    <el-result icon="warning" title="404" sub-title="这个页面不存在">
      <template #extra>
        <RouterLink to="/chat">
          <el-button type="primary">回到对话</el-button>
        </RouterLink>
      </template>
    </el-result>
  </div>
</template>

<style scoped>
.notfound {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
}
</style>

