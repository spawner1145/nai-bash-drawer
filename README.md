# nai bash drawer
批量跑图，保存到zip文件，并生成一个csv文件对应图片和tag，支持使用wildcard

用于刷数据集

kaggle地址https://www.kaggle.com/code/spawnerqwq/nai4drawer

## 特殊用法
#### 注意:是当作提示词用的,用的时候也不要加大括号
```yaml
<wd{weight1}:{name}={count}>
```
此指令会固定从名为name(不用加txt后缀)的wildcard中抽取count项，附加weight1的固定权重

```yaml
<wd{weight1}-{weight2}:{name}={count}>
```
此指令会从名为name的wildcard中抽取count项，附加weight1到weight2范围内的随机权重
如果权重参数（weight1-weight2或weight1）出现问题，默认为权重范围0到1

举例：
```yaml
<wd1:artist_full=1> # 随机抽一个画师，权重为1，例如wlop
<wd1:artist_full=2> # 随机抽两个画师，权重为1，例如wlop,torino aqua
<wd0.5:artist_full=2> # 随机抽两个画师，权重为0.5，例如(wlop:0.5),(torino aqua:0.5)
<wd0.4-0.5:artist_full=3> # 随机抽3个画师，权重为0.4到0.5中的随机数，例如(a:0.4111),(b:0.4231),(c:0.4342)
<wd1:artist_full=2>,<wd0.6:artist_full=3> # 随机抽五个画师，两个权重为1，三个权重为0.6
```
