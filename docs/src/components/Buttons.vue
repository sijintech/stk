<template>
  <div class="box">
    <div class="flex">
      <a :href="lang === 'cn' ? 'en/dev_guide/' : '/dev_guide/'"
         class="download-button gray watch-video">
        <div class="icon">
        </div><span>{{lang['开发者手册']}}</span>
      </a>
      <a :href="lang === 'cn' ? '/zh-cn/user_guide/' : '/user_guide/'"
         class="download-button gray watch-video">
        <div class="icon">
        </div><span>{{lang['用户手册']}}</span>
      </a>
    </div>
    <p v-html="lang['提示']">
    </p>
  </div>

</template>
<script>
import i18n from "../content/i18n";

export default {
  props: {
    lang: String,
  },
  data () {
    return {
      lang: {},
    }
  },
  created () {
    this.lang = i18n[this.$props.lang]
  },

}
</script>
<style  scoped>
.box {
  position: relative;
  top: -270px;
}
.box p {
  text-align: center;
  font-size: 14px;
  font-weight: 400;
  color: #4a5263;
  line-height: 1.5;
}
.flex {
  display: flex;
  align-items: center;

  justify-content: center;

  flex-wrap: wrap;
}
.dropdown-item {
  color: #2c313a;
}
.download-button,
a.download-button {
  -webkit-user-drag: none;
  -webkit-user-select: none;
  position: relative;
  display: inline-block;
  height: 48px;
  line-height: 46px;
  padding-right: 24px;
  padding-left: 24px;
  text-align: left;
  border: 1px solid transparent;
  margin: 0 10px;
  border-radius: 5px;
  font-size: 16px;
  color: #ffffff;
  text-decoration: none;
}

@media (min-width: 640px) and (max-width: 992px) {
  .download-button,
  a.download-button {
    margin-bottom: 10px;
  }
}

@media only screen and (max-width: 767px) {
  .download-button,
  a.download-button {
    font-size: 16px;
  }

  .download-button.watch-video,
  a.download-button.watch-video {
    margin-top: 10px;
  }
}

.download-button:last-child,
a.download-button:last-child {
  margin-right: 0;
}

.download-button:hover,
a.download-button:hover {
  cursor: pointer;
}

.download-button .icon,
a.download-button .icon {
  line-height: 44px;
  text-align: center;
  float: left;
  margin-right: 10px;
}

.download-button .icon img,
a.download-button .icon img {
  display: inline-block;
  vertical-align: middle;
}

.download-button .download-others,
a.download-button .download-others {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  width: 20px;
  text-align: center;
  background: rgba(0, 0, 0, 0.1);
  cursor: pointer;
}

.download-button .download-others span.tri,
a.download-button .download-others span.tri {
  position: absolute;
  top: 50%;
  left: 50%;
  font-size: 16px;
  transform: translateX(-50%) translateY(-50%);
}

.download-button .download-others:hover,
a.download-button .download-others:hover {
  background: rgba(0, 0, 0, 0.15);
}

.download-button .download-dropdown,
a.download-button .download-dropdown {
  position: absolute;
  background: #fff;
  top: 100%;
  right: 0;
  margin-top: 4px;
  z-index: 100;
  min-width: 160px;
  border: 1px solid #d3dce6;
  box-shadow: 0 2px 4px 0 rgba(0, 0, 0, 0.12), 0 0 6px 0 rgba(0, 0, 0, 0.04);
  border-radius: 3px;
  padding: 2px 0;
}

.download-button .download-dropdown .dropdown-item,
a.download-button .download-dropdown .dropdown-item {
  padding: 0 16px;
  font-size: 16px;
  height: 44px;
  line-height: 44px;
}

.download-button .download-dropdown .dropdown-item:hover,
a.download-button .download-dropdown .dropdown-item:hover {
  cursor: pointer;
  background-color: #f9fafc;
}

.download-button.gray,
a.download-button.gray {
  color: #2c313a;
  border: 1px solid #ccc;
  background-color: #0072ef;
}

.download-button.blue,
a.download-button.blue {
  background-color: #0072ef;
  border: 1px solid transparent;
  color: #fff;
  padding-right: 40px;
}

.download-button.white,
a.download-button.white {
  background-color: #fff;
  border: 1px solid transparent;
  color: #0072ef;
}

.download-button.white-outline,
a.download-button.white-outline {
  border: 1px solid #fff;
  background-color: transparent;
  color: #fff;
}
</style>