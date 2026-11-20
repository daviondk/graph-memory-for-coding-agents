def minPath(grid, k):
    n = len(grid)
    pos = {}
    for i in range(n):
        for j in range(n):
            pos[grid[i][j]] = (i, j)
    
    # Find the cell with value 1
    start = pos[1]
    
    # Find the minimum neighbor of cell 1
    min_neighbor = n * n + 1
    for di, dj in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        ni, nj = start[0] + di, start[1] + dj
        if 0 <= ni < n and 0 <= nj < n:
            if grid[ni][nj] < min_neighbor:
                min_neighbor = grid[ni][nj]
    
    ans = []
    for i in range(k):
        if i % 2 == 0:
            ans.append(1)
        else:
            ans.append(min_neighbor)
    return ans
