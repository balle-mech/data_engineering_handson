# データエンジニアリング実習

## フォルダ構造

```
data_engineering_handson/
├── README.md                          # このリポジトリ全体の説明ファイル
├── notebooks/                         # ノートブック編で使用
│   ├── ハンズオンガイド(Notebook編).md   # こちらを参照しながら進めてください。
│   ├── # 各データ取り込み・加工ハンズオンノートブック
│   └── example_answer/                # 正解例・サンプルコード
│
├── sample_csv/            # ダミーCSVファイル、生成プログラム
└── sample_taka-yayoi/     # 本リポジトリフォーク元にあった、taka-yayoiさんのサンプルコードです。
```

---

## データエンジニアリングハンズオンNotebook編

`notebooks`フォルダ配下の`ハンズオンガイド(Notebook編).md`をご参照ください。

## データエンジニアリングハンズオン(Spark Declarative Pipelines編)

https://github.com/balle-mech/data-engineering-handson-sdp.git

## トラブルシューティング

### テーブルが作成されない

- パイプラインが正常に完了しているか確認（緑色のチェックマーク）
- エラーメッセージがあれば内容を確認

### CSVファイルの値が文字化け

VSCodeで開いたとき、日本語が文字化けしてしまうことがあります。

```csv
event_time,event_type,event_name,action_name,user,request_params,resource_name,source_ip
2026-02-02T21:08:36,access,table_access,getTable,"{""email"": ""user00@example.com"", ""name"": ""���X�� ��""}","{""full_name_arg"": ""dev.sales.table_016""}",dev.sales.table_016,10.6.121.14
2026-02-02T23:56:39,access,table_access,getTable,"{""email"": ""user00@example.com"", ""name"": ""���X�� ��""}","{""full_name_arg"": ""prod.sales.table_019""}",prod.sales.table_019,10.4.222.123
```

（userカラムのname部分）

文字コードがUTF-8（）で表示されていることが原因であれば、以下手順でShisft JIS（日本語）に変更することで解消するかもしれません。
**注意：**既に文字化けした状態で保存までされている場合は、この操作では解消できないです。

画面下の「UTF-8」をクリック、「エンコード付きで保存を選択」
![エンコード付きで保存](./img/エンコード付きで保存.png)

![Japaneseで保存](./img/Japaneseで保存.png)

---

## 参考リンク

- [Lakeflow SDP入門：基礎から実践まで](https://qiita.com/taka_yayoi/items/e15caec3c71a27aa12b1)
- [SQLだけで始めるLakeflow SDP](https://qiita.com/taka_yayoi/items/e6368446040c9e979d0f)
- [Lakeflow SDPでデータ品質を守るエクスペクテーション](https://qiita.com/taka_yayoi/items/0b525cb05a095ad0bbe1)
