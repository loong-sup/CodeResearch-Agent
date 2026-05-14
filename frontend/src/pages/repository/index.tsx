import * as api from '@/api'
import IconDelete from '@/assets/repository/action/delete.svg'
import { PlusOutlined } from '@ant-design/icons'
import { useRequest } from 'ahooks'
import { Button, Modal, Space, Table } from 'antd'
import { ColumnsType } from 'antd/es/table'
import { TableRowSelection } from 'antd/es/table/interface'
import dayjs from 'dayjs'
import { useMemo, useRef, useState } from 'react'
import { FileIcon } from './components/file-icon'
import { Status } from './components/status'
import RepositoryUpload, { RepositoryUploadRef } from './components/upload'
import styles from './index.module.scss'

type IRepository = API.Repository & {
  id: number
  $suffix: FileIcon
  method: string
  enable: boolean
  status: string
}

export default function Index() {
  const { data, refresh } = useRequest(async () => {
    const { data } = await api.repository.list()
    return data?.map(
      (item, index) =>
        ({
          ...item,
          $suffix: item.file_name.split('.').pop() as FileIcon,
          id: index + 1,
          method: '代码结构切块',
          enable: true,
          status: 'success',
        }) satisfies IRepository,
    )
  })

  const deleteFile = async (file: IRepository) => {
    const {
      data: { message = '删除成功' },
    } =
      (await api.repository.deleteFile({
        file_name: file.file_name,
      })) || {}
    // 提示成功
    window.$app.message.success(message)
    refresh()
  }

  const columns = useMemo<ColumnsType<IRepository>>(
    () => [
      {
        title: '名称',
        dataIndex: 'file_name',
        width: 200,
        render(value, row) {
          return (
            <div className={styles['repository-page__file-name']} title={value}>
              <FileIcon className={styles['icon']} suffix={row.$suffix} />
              {value}
            </div>
          )
        },
      },
      {
        title: '更新时间',
        dataIndex: 'updated_at',
        width: 200,
        render(value) {
          return dayjs(value).format('MM/DD/YYYY HH:mm:ss')
        },
      },
      {
        title: '切块策略',
        dataIndex: 'method',
        width: 100,
        render(value) {
          return value ?? '代码结构切块'
        },
      },
      {
        title: '状态',
        dataIndex: 'status',
        width: 100,
        render(value) {
          return <Status status={value} />
        },
      },
      {
        title: '操作',
        dataIndex: 'action',
        width: 100,
        render(_, row) {
          return (
            <Space>
              <Button
                color="default"
                variant="text"
                shape="circle"
                size="small"
                onClick={() => deleteFile(row)}
              >
                <img src={IconDelete} />
              </Button>
            </Space>
          )
        },
      },
    ],
    [],
  )
  const scroll = useMemo(() => {
    return {
      x: columns?.reduce((prev, current) => {
        return prev + parseInt(String(current.width ?? 0))
      }, 0),
    }
  }, [columns])

  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([])

  const onSelectChange = (newSelectedRowKeys: React.Key[]) => {
    setSelectedRowKeys(newSelectedRowKeys)
  }
  const rowSelection: TableRowSelection<IRepository> = {
    selectedRowKeys,
    onChange: onSelectChange,
  }

  /* 上传 */
  const [openUpload, setOpenUpload] = useState(false)
  const uploadRef = useRef<RepositoryUploadRef>(null)
  const [uploading, setUploading] = useState(false)

  return (
    <div className={styles['repository-page']}>
      <div className={styles['repository-page__header']}>
        <div className={styles['title']}>代码仓库</div>
        <div className={styles['desc']}>
          上传源码仓库、项目压缩包或 Markdown 文档，完成索引后再开始代码问答。
        </div>
      </div>

      <div className={styles['repository-page__body']}>
        <div className={styles['header']}>
          <Button type="primary" onClick={() => setOpenUpload(true)}>
            <PlusOutlined />
            上传仓库
          </Button>
        </div>

        <Table<IRepository>
          rowKey="id"
          columns={columns}
          dataSource={data}
          rowSelection={rowSelection}
          scroll={scroll}
          pagination={false}
        />
      </div>

      <Modal
        title="上传仓库或项目文档"
        open={openUpload}
        okText="开始索引"
        width={400}
        destroyOnClose
        onCancel={() => {
          if (uploading) return
          setOpenUpload(false)
        }}
        onOk={async () => {
          setUploading(true)
          try {
            await uploadRef.current?.submit()
            setOpenUpload(false)
            refresh()
          } finally {
            setUploading(false)
          }
        }}
      >
        <RepositoryUpload beforeUpload={() => false} ref={uploadRef} />
      </Modal>
    </div>
  )
}
