// @ts-nocheck
// 导入必要的模块
import fetch from 'node-fetch';
import { getOctokit, context } from '@actions/github';

// 定义更新信息的标签和文件名
const UPDATE_TAG_NAME = 'updater';
const UPDATE_FILE_NAME = 'update.json';

// 获取签名的函数
const getSignature = async (url) => {
  const response = await fetch(url, {
    method: 'GET',
    headers: { 'Content-Type': 'application/octet-stream' }
  });
  return response.text();
};

// 初始化更新数据对象
const updateData = {
  name: '',
  pub_date: new Date().toISOString(),
  platforms: {
    win64: { signature: '', url: '' },
    linux: { signature: '', url: '' },
    darwin: { signature: '', url: '' },
    'linux-x86_64': { signature: '', url: '' },
    'windows-x86_64': { signature: '', url: '' }
  }
};

// 获取 GitHub 操作的 Octokit 实例和选项
// Octokit 是 GitHub 的官方 REST API 客户端库，使开发者能够方便地与 GitHub 进行交互。
const octokit = getOctokit(process.env.GITHUB_TOKEN);
// context.repo 对象提供了有关当前存储库的信息，包括所有者和存储库名称
const options = { owner: context.repo.owner, repo: context.repo.repo };

// 获取最新发布的信息
// release 变量现在包含了仓库的最新发布信息，可以通过访问 release 对象的属性来获取相关信息，比如发布的标签名 (release.tag_name)、发布时间 (release.published_at) 等。
const { data: release } = await octokit.rest.repos.getLatestRelease(options);
updateData.name = release.tag_name;
// 遍历发布的资产，更新更新数据对象的信息
for (const { name, browser_download_url } of release.assets) {
  // 处理每个资产
  if (name.endsWith('.msi.zip')) {
    // 处理以 .msi.zip 结尾的资产
    // 更新 updateData.platforms.win64.url 和 updateData.platforms['windows-x86_64'].url
    updateData.platforms.win64.url = browser_download_url;
    updateData.platforms['windows-x86_64'].url = browser_download_url;
  } else if (name.endsWith('.msi.zip.sig')) {
    // 处理以 .msi.zip.sig 结尾的资产
    // 获取签名并更新相应的字段
    const signature = await getSignature(browser_download_url);
    updateData.platforms.win64.signature = signature;
    updateData.platforms['windows-x86_64'].signature = signature;
  } else if (name.endsWith('.app.tar.gz')) {
    // 处理以 .app.tar.gz 结尾的资产
    // 更新 updateData.platforms.darwin.url
    updateData.platforms.darwin.url = browser_download_url;
  } else if (name.endsWith('.app.tar.gz.sig')) {
    // 处理以 .app.tar.gz.sig 结尾的资产
    // 获取签名并更新相应的字段
    const signature = await getSignature(browser_download_url);
    updateData.platforms.darwin.signature = signature;
  } else if (name.endsWith('.AppImage.tar.gz')) {
    // 处理以 .AppImage.tar.gz 结尾的资产
    // 更新 updateData.platforms.linux.url 和 updateData.platforms['linux-x86_64'].url
    updateData.platforms.linux.url = browser_download_url;
    updateData.platforms['linux-x86_64'].url = browser_download_url;
  } else if (name.endsWith('.AppImage.tar.gz.sig')) {
    // 处理以 .AppImage.tar.gz.sig 结尾的资产
    // 获取签名并更新相应的字段
    const signature = await getSignature(browser_download_url);
    updateData.platforms.linux.signature = signature;
    updateData.platforms['linux-x86_64'].signature = signature;
  }
}


// 获取更新器的信息
// options 对象包含了一些仓库的信息，包括所有者（owner）和仓库名称（repo）。通过使用解构赋值 { ...options, tag: UPDATE_TAG_NAME }，将 tag 属性添加到 options 对象中，以指定要获取的发布的标签
const { data: updater } = await octokit.rest.repos.getReleaseByTag({
  ...options,
  tag: UPDATE_TAG_NAME
});

// 删除已有的更新文件
for (const { id, name } of updater.assets) {
  if (name === UPDATE_FILE_NAME) {
    await octokit.rest.repos.deleteReleaseAsset({ ...options, asset_id: id });
    break;
  }
}

// 上传新的更新文件
await octokit.rest.repos.uploadReleaseAsset({
  ...options,
  release_id: updater.id,
  name: UPDATE_FILE_NAME,
  data: JSON.stringify(updateData)
});
