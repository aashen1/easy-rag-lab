# 问题

> 2026年4月18日

这个项目跑着跑着，根目录就会多出一个`output_dir`空文件夹，里面也不会产生东西，删了再跑一会儿又会出来。又因为这个名字在代码里使用太多，AI尝试排查了一会儿没有成功。

# AI分析

找Qwen要了一套方案，见 [chat-幽灵文件夹排查指南.md](chat-幽灵文件夹排查指南.md) 

先让AI按照这个方案在python代码里埋了钩子，但没能成功捕获，不知道是代码运作不对，还是日志系统记录不完整。

于是又下载了`Process Monitor`，按`Ctrl+L`，设置过滤条件：

```
Operation is CreateFile
Result is SUCCESS
Path ends with output_dir
```

点击`Apply`，然后继续跑测试。

目前已经确定

`pixi run pytest tests/ -m "not integration" -v`

这项测试可以稳定地触发创建`output_dir`的现象。

于是就开一个终端不停地运行这条测试，不断把出现的文件夹删除。

线索：

1. 创建文件夹的时候是有创建时间的；
2. ProcMon在上面的配置下（加上打开最顶上那一行的各种Show，总之能捕捉的全捕捉），可以捕捉到数个相关日志，关闭Typora和Explorer等无关项目，发现剩下的只有`python.exe`，也就是说并不是IDE之类的东西，而确实就是程序本身创建的。
3. 其中有一条捕捉到的信息，和出现的文件夹的创建时间在同一秒，定位为怀疑对象。
4. 将procmon给出的stack信息发给Qwen（更新在chat记录里了），但AI表示在这边好像抓不住，还是要用钩子代码。

1:39 周六

有点累，在procmon这边排查半天好像毫无进展。

1:43 周六

难绷，原来这个钩子代码设置的是根目录下面的单独一个log文件，名字叫`output_dir_debug.log`我到现在才反应过来，之前procmon筛选的时候都没意识到这个文件是干啥的。

1:44 周六

把日志丢给TRAE，移动了一行代码，但经过测试没有解决问题，更糟糕的是现在连debug log也不产生了。

1:54 周六

还好，追问了一下AI，帮我找到了一个钩子没有覆盖的创建方式，修复之后，

问题终于解决了。



# AI总结

让我重新排查。既然日志不生成了，说明可能不是通过 `os.mkdir` 创建的，而是通过 `pathlib.Path.mkdir`。让我检查 debug hook 代码：

发现问题了！debug hook 只 hook 了 `os.mkdir` 和 `os.makedirs`，但 `src/utils.py` 中使用的是 `pathlib.Path.mkdir`！让我检查：

**修复完成！**

## 问题根源

幽灵文件夹 `output_dir` 由两个测试用例创建：

1. `tests/test_parser.py:51` - `test_parse_all_pdfs_input_dir_not_found`
2. `tests/test_chunker.py:65` - `test_process_parsed_files_input_dir_not_found`

两个函数都有相同的 bug：**先创建输出目录，后检查输入目录是否存在**。

## 修复内容

| 文件                                                         | 函数                   | 修改                           |
| ------------------------------------------------------------ | ---------------------- | ------------------------------ |
| [src/parser.py:41-48](file:///b:/project/ash-easy-rag/src/parser.py#L41-L48) | `parse_all_pdfs`       | 先检查输入目录，再创建输出目录 |
| [src/chunker.py:86-93](file:///b:/project/ash-easy-rag/src/chunker.py#L86-L93) | `process_parsed_files` | 先检查输入目录，再创建输出目录 |

## 结果

- ✅ 所有 32 个测试通过
- ✅ 幽灵文件夹 `output_dir` 不再被错误创建
